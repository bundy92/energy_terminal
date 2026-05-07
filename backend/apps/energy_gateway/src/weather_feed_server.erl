%% @doc Open-Meteo weather feed GenServer.
%%
%% Fetches current and forecast temperature data for key energy demand
%% centres.  Publishes heating degree days (HDD) and cooling degree days
%% (CDD) relative to a 65°F (18.3°C) base, which are the standard
%% industry measures for residential energy demand.
%%
%% == Monitored locations ==
%%
%% New York (37.78, -122.41), Chicago (41.88, -87.63),
%% Houston (29.76, -95.37), London (51.51, -0.12),
%% Rotterdam (51.92, 4.48), Tokyo (35.69, 139.69).
%%
%% == Published event payload ==
%%
%% ```
%% #{
%%     location    => binary(),
%%     temp_c      => float(),
%%     hdd         => float(),
%%     cdd         => float(),
%%     forecast_7d => [float()]   %% daily mean temps
%% }
%% '''
-module(weather_feed_server).
-behaviour(gen_server).

-export([start_link/0, force_poll/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,   ?MODULE).
-define(BASE_URL, "https://api.open-meteo.com/v1/forecast").
-define(BASE_TEMP_C, 18.3).  %% 65°F base for HDD/CDD
-define(ENDPOINT, open_meteo).

-define(LOCATIONS, [
    #{name => <<"New York">>,  lat =>  40.71, lon =>  -74.01},
    #{name => <<"Chicago">>,   lat =>  41.88, lon =>  -87.63},
    #{name => <<"Houston">>,   lat =>  29.76, lon =>  -95.37},
    #{name => <<"London">>,    lat =>  51.51, lon =>   -0.12},
    #{name => <<"Rotterdam">>, lat =>  51.92, lon =>    4.48},
    #{name => <<"Tokyo">>,     lat =>  35.69, lon =>  139.69}
]).

%%=============================================================================
%% Public API
%%=============================================================================

-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

-spec force_poll() -> ok.
force_poll() ->
    gen_server:cast(?SERVER, poll).

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init([]) -> {ok, map()}.
init([]) ->
    erlang:send_after(3000, self(), poll),
    %% Weather changes slowly; poll every 3 hours
    {ok, #{interval => 10_800_000}}.

handle_call(_Req, _From, State) -> {reply, ok, State}.
handle_cast(poll, State) -> do_poll(), {noreply, State}.

handle_info(poll, #{interval := Interval} = State) ->
    do_poll(),
    erlang:send_after(Interval, self(), poll),
    {noreply, State};

handle_info(_Info, State) -> {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.

%%=============================================================================
%% Internal helpers
%%=============================================================================

-spec do_poll() -> ok.
do_poll() ->
    lists:foreach(fun fetch_location/1, ?LOCATIONS).

-spec fetch_location(Location :: map()) -> ok.
fetch_location(#{name := Name, lat := Lat, lon := Lon}) ->
    case rate_limiter:check_and_consume(?ENDPOINT) of
        {error, rate_limited} ->
            lager:warning("Open-Meteo rate limited for ~s", [Name]);
        ok ->
            Url = io_lib:format(
                "~s?latitude=~.2f&longitude=~.2f"
                "&current=temperature_2m"
                "&daily=temperature_2m_max,temperature_2m_min"
                "&forecast_days=7&timezone=auto",
                [?BASE_URL, Lat, Lon]
            ),
            fetch_and_publish(lists:flatten(Url), Name)
    end.

-spec fetch_and_publish(Url :: string(), Name :: binary()) -> ok.
fetch_and_publish(Url, Name) ->
    case hackney:get(Url, [], <<>>, [with_body]) of
        {ok, 200, _, Body} ->
            parse_weather(Body, Name);
        {ok, Status, _, _} ->
            lager:warning("Open-Meteo ~p returned ~p", [Name, Status]);
        {error, Reason} ->
            lager:error("Open-Meteo error for ~p: ~p", [Name, Reason])
    end.

-spec parse_weather(Body :: binary(), Name :: binary()) -> ok.
parse_weather(Body, Name) ->
    try
        D       = jsx:decode(Body, [return_maps]),
        TempC   = get_nested(D, [<<"current">>, <<"temperature_2m">>]),
        MaxList = maps:get(<<"temperature_2m_max">>,
                           maps:get(<<"daily">>, D, #{}), []),
        MinList = maps:get(<<"temperature_2m_min">>,
                           maps:get(<<"daily">>, D, #{}), []),
        MeanList = lists:zipwith(fun(Mx, Mn) -> (Mx + Mn) / 2 end,
                                 MaxList, MinList),
        HDD = max(0, ?BASE_TEMP_C - TempC),
        CDD = max(0, TempC - ?BASE_TEMP_C),
        Payload = #{
            location    => Name,
            temp_c      => TempC,
            hdd         => HDD,
            cdd         => CDD,
            forecast_7d => MeanList
        },
        ets_cache:put({weather, Name}, Payload),
        data_router:publish(#{
            type      => weather,
            source    => open_meteo,
            symbol    => Name,
            timestamp => erlang:system_time(millisecond),
            payload   => Payload
        })
    catch C:E ->
        lager:error("Weather parse error ~p: ~p:~p", [Name, C, E])
    end.

-spec get_nested(map(), [binary()]) -> term().
get_nested(V, [])      -> V;
get_nested(M, [K | T]) -> get_nested(maps:get(K, M, undefined), T).
