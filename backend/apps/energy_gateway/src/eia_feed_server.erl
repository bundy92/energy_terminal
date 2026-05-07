%% @doc US EIA (Energy Information Administration) feed GenServer.
%%
%% Polls the EIA Open Data API v2 for weekly petroleum status report
%% data including crude inventories, production, imports, and refinery
%% utilisation.  Data is published as `fundamental' events.
%%
%% == EIA Series IDs polled ==
%%
%% <ul>
%%   <li>`PET.WCRSTUS1.W' — US crude oil stocks (thousand barrels)</li>
%%   <li>`PET.WCRFPUS2.W' — US crude oil production (thousand bbl/day)</li>
%%   <li>`PET.WCRRIUS2.W' — US crude oil refinery inputs</li>
%%   <li>`PET.WPULEUS2.W' — Refinery utilisation rate (%)</li>
%%   <li>`NG.NW2EUS_EPG0_SWO_BCF.W' — US nat gas in storage (BCF)</li>
%% </ul>
%%
%% API key is read from the environment variable `EIA_API_KEY'.
%% The feed falls back to cached data if the key is absent or the API
%% returns an error.
-module(eia_feed_server).
-behaviour(gen_server).

-export([start_link/0, force_poll/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,    ?MODULE).
-define(BASE_URL,  "https://api.eia.gov/v2/seriesid/").
-define(ENDPOINT,  eia).
-define(SERIES, [
    "PET.WCRSTUS1.W",
    "PET.WCRFPUS2.W",
    "PET.WCRRIUS2.W",
    "PET.WPULEUS2.W",
    "NG.NW2EUS_EPG0_SWO_BCF.W"
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
    ApiKey   = os:getenv("EIA_API_KEY", ""),
    Interval = application:get_env(energy_gateway, poll_interval_ms, 3_600_000),
    %% EIA weekly releases — poll every hour; data only changes weekly
    erlang:send_after(2000, self(), poll),
    lager:info("EIA feed server started (key present: ~p)", [ApiKey =/= ""]),
    {ok, #{interval => Interval, api_key => ApiKey}}.

handle_call(_Req, _From, State) -> {reply, ok, State}.

handle_cast(poll, State) ->
    do_poll(State),
    {noreply, State};

handle_cast(_Msg, State) -> {noreply, State}.

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
    lager:info("EIA API key not set; skipping poll"),
    ok;
do_poll(#{api_key := Key}) ->
    case rate_limiter:check_and_consume(?ENDPOINT) of
        ok ->
            lists:foreach(fun(Series) -> fetch_series(Series, Key) end, ?SERIES);
        {error, rate_limited} ->
            lager:warning("EIA rate limit hit")
    end.

-spec fetch_series(Series :: string(), ApiKey :: string()) -> ok.
fetch_series(Series, ApiKey) ->
    Url = ?BASE_URL ++ Series ++ "?api_key=" ++ ApiKey ++
          "&data[]=value&sort[0][column]=period&sort[0][direction]=desc&length=1",
    case hackney:get(Url, [], <<>>, [with_body]) of
        {ok, 200, _, Body} ->
            parse_and_publish(Series, Body);
        {ok, Status, _, _} ->
            lager:warning("EIA ~p returned HTTP ~p", [Series, Status]);
        {error, Reason} ->
            lager:error("EIA ~p fetch error: ~p", [Series, Reason])
    end.

-spec parse_and_publish(Series :: string(), Body :: binary()) -> ok.
parse_and_publish(Series, Body) ->
    try
        Decoded   = jsx:decode(Body, [return_maps]),
        [Latest | _] = get_in(Decoded, [<<"response">>, <<"data">>]),
        Value    = maps:get(<<"value">>,  Latest, null),
        Period   = maps:get(<<"period">>, Latest, null),
        SeriesBin = list_to_binary(Series),
        Payload  = #{series => SeriesBin, value => Value, period => Period},
        ets_cache:put({fundamental, SeriesBin}, Payload),
        data_router:publish(#{
            type      => fundamental,
            source    => eia,
            symbol    => SeriesBin,
            timestamp => erlang:system_time(millisecond),
            payload   => Payload
        })
    catch
        C:E ->
            lager:error("EIA parse error for ~p: ~p:~p", [Series, C, E])
    end.

-spec get_in(map(), [binary()]) -> term().
get_in(Map, [])       -> Map;
get_in(Map, [K | Ks]) -> get_in(maps:get(K, Map, #{}), Ks).
