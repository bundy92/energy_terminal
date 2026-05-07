%% @doc Federal Reserve FRED macro data feed GenServer.
%%
%% Fetches macro indicator series from the FRED API that contextualise
%% energy price movements: USD index, CPI, real interest rates, and
%% industrial production.
%%
%% == Series polled ==
%%
%% <ul>
%%   <li>`DTWEXBGS'  — Nominal Broad USD Index (daily)</li>
%%   <li>`CPIAUCSL'  — CPI All Urban Consumers (monthly)</li>
%%   <li>`REAINTRATREARAT10Y' — 10-yr real interest rate (daily)</li>
%%   <li>`INDPRO'    — Industrial Production Index (monthly)</li>
%%   <li>`DCOILWTICO' — WTI spot (cross-check / baseline)</li>
%% </ul>
%%
%% API key set via `FRED_API_KEY' environment variable.
-module(fred_feed_server).
-behaviour(gen_server).

-export([start_link/0, force_poll/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,   ?MODULE).
-define(BASE_URL, "https://api.stlouisfed.org/fred/series/observations").
-define(ENDPOINT, fred).

-define(SERIES_IDS, [
    "DTWEXBGS",
    "CPIAUCSL",
    "REAINTRATREARAT10Y",
    "INDPRO",
    "DCOILWTICO"
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
    ApiKey = os:getenv("FRED_API_KEY", ""),
    %% FRED data updates daily; poll every 4 hours
    erlang:send_after(4000, self(), poll),
    lager:info("FRED feed started (key present: ~p)", [ApiKey =/= ""]),
    {ok, #{interval => 14_400_000, api_key => ApiKey}}.

handle_call(_Req, _From, State) -> {reply, ok, State}.
handle_cast(poll, State) -> do_poll(State), {noreply, State}.

handle_info(poll, #{interval := Interval} = State) ->
    do_poll(State),
    erlang:send_after(Interval, self(), poll),
    {noreply, State};

handle_info(_Info, State) -> {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.

%%=============================================================================
%% Internal helpers
%%=============================================================================

-spec do_poll(State :: map()) -> ok.
do_poll(#{api_key := ""}) ->
    lager:info("FRED API key absent; skipping"),
    ok;
do_poll(#{api_key := Key}) ->
    lists:foreach(fun(S) ->
        case rate_limiter:check_and_consume(?ENDPOINT) of
            ok               -> fetch_series(S, Key);
            {error, _}       -> lager:warning("FRED rate limited for ~s", [S])
        end
    end, ?SERIES_IDS).

-spec fetch_series(SeriesId :: string(), ApiKey :: string()) -> ok.
fetch_series(SeriesId, ApiKey) ->
    Url = ?BASE_URL ++ "?series_id=" ++ SeriesId ++
          "&api_key=" ++ ApiKey ++
          "&file_type=json&sort_order=desc&limit=1",
    case hackney:get(Url, [], <<>>, [with_body]) of
        {ok, 200, _, Body} ->
            parse_and_publish(SeriesId, Body);
        {ok, Status, _, _} ->
            lager:warning("FRED ~p returned HTTP ~p", [SeriesId, Status]);
        {error, Reason} ->
            lager:error("FRED ~p error: ~p", [SeriesId, Reason])
    end.

-spec parse_and_publish(SeriesId :: string(), Body :: binary()) -> ok.
parse_and_publish(SeriesId, Body) ->
    try
        D          = jsx:decode(Body, [return_maps]),
        [Obs | _]  = maps:get(<<"observations">>, D, []),
        Value      = maps:get(<<"value">>,  Obs, <<".">>),
        Date       = maps:get(<<"date">>,   Obs, <<"">>),
        SeriesBin  = list_to_binary(SeriesId),
        %% FRED uses "." for missing; convert to null
        NumValue   = case Value of
            <<".">> -> null;
            V       -> binary_to_float_safe(V)
        end,
        Payload = #{series => SeriesBin, value => NumValue, date => Date},
        ets_cache:put({macro, SeriesBin}, Payload),
        data_router:publish(#{
            type      => macro,
            source    => fred,
            symbol    => SeriesBin,
            timestamp => erlang:system_time(millisecond),
            payload   => Payload
        })
    catch C:E ->
        lager:error("FRED parse error ~p: ~p:~p", [SeriesId, C, E])
    end.

-spec binary_to_float_safe(B :: binary()) -> float() | null.
binary_to_float_safe(B) ->
    try
        case binary:match(B, <<".">>) of
            nomatch -> float(binary_to_integer(B));
            _       -> binary_to_float(B)
        end
    catch _:_ -> null
    end.
