%% @doc IEA (International Energy Agency) Open Data feed GenServer.
%%
%% Polls the IEA Open Data API for global oil and gas supply, demand,
%% and stock data.  The IEA publishes monthly Oil Market Reports and
%% quarterly Gas Market Reports; this feed retrieves the most recent
%% available observations for key balances.
%%
%% == Datasets polled ==
%%
%% <ul>
%%   <li>Monthly Oil Statistics — OECD total industry stocks</li>
%%   <li>Oil Market Report — global demand and supply balance</li>
%%   <li>World Energy Statistics — non-OECD production by region</li>
%% </ul>
%%
%% == Authentication ==
%%
%% An IEA Open Data API key is required.  Set via the environment
%% variable `IEA_API_KEY'.  Without a key the feed logs a warning and
%% deactivates itself — no crash, no supervisor restart storm.
%%
%% == Rate limit ==
%%
%% The IEA free tier allows 10 requests per minute.  The rate limiter
%% is consulted before every request.
-module(iea_feed_server).
-behaviour(gen_server).

-export([start_link/0, force_poll/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,   ?MODULE).
-define(BASE_URL, "https://api.iea.org/stats/").
-define(ENDPOINT, iea).

%% IEA dataset / product / flow / unit combinations
-define(QUERIES, [
    {"OILFUTURES", "OECD_STOCKS",  "TOTIND",  "KBBL"},
    {"OILFUTURES", "WORLD_DEMAND", "TOTAL",   "MBDOE"},
    {"OILFUTURES", "WORLD_SUPPLY", "TOTAL",   "MBDOE"}
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

-spec init([]) -> {ok, map()} | {stop, no_api_key}.
init([]) ->
    ApiKey = os:getenv("IEA_API_KEY", ""),
    case ApiKey of
        "" ->
            lager:warning("IEA feed: IEA_API_KEY not set — feed inactive"),
            %% Stay alive but never poll; prevents supervisor restart loops
            {ok, #{active => false, api_key => ""}};
        Key ->
            %% IEA data updates monthly; poll every 6 hours
            erlang:send_after(5000, self(), poll),
            lager:info("IEA feed server started"),
            {ok, #{active => true, api_key => Key, interval => 21_600_000}}
    end.

handle_call(_Req, _From, State) -> {reply, ok, State}.

handle_cast(poll, #{active := true} = State) ->
    do_poll(State),
    {noreply, State};

handle_cast(poll, #{active := false} = State) ->
    {noreply, State};

handle_cast(_Msg, State) -> {noreply, State}.

handle_info(poll, #{active := true, interval := Interval} = State) ->
    do_poll(State),
    erlang:send_after(Interval, self(), poll),
    {noreply, State};

handle_info(poll, #{active := false} = State) ->
    {noreply, State};

handle_info(_Info, State) -> {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.

%%=============================================================================
%% Internal helpers
%%=============================================================================

-spec do_poll(State :: map()) -> ok.
do_poll(#{api_key := Key}) ->
    lists:foreach(fun({Dataset, Product, Flow, Unit}) ->
        case rate_limiter:check_and_consume(?ENDPOINT) of
            ok ->
                fetch_and_publish(Dataset, Product, Flow, Unit, Key);
            {error, rate_limited} ->
                lager:warning("IEA rate limit hit for ~s/~s", [Dataset, Product])
        end
    end, ?QUERIES).

-spec fetch_and_publish(string(), string(), string(), string(), string()) -> ok.
fetch_and_publish(Dataset, Product, Flow, Unit, ApiKey) ->
    Url = ?BASE_URL ++ Dataset ++
          "?products=" ++ Product ++
          "&flows="    ++ Flow ++
          "&unit="     ++ Unit ++
          "&last=1",
    Headers = [
        {"Authorization", "Bearer " ++ ApiKey},
        {"Accept", "application/json"}
    ],
    case hackney:get(Url, Headers, <<>>, [with_body]) of
        {ok, 200, _, Body} ->
            parse_and_publish(Dataset, Product, Flow, Body);
        {ok, 401, _, _} ->
            lager:error("IEA API key rejected (401)");
        {ok, Status, _, _} ->
            lager:warning("IEA ~s returned HTTP ~p", [Dataset, Status]);
        {error, Reason} ->
            lager:error("IEA fetch error: ~p", [Reason])
    end.

-spec parse_and_publish(string(), string(), string(), binary()) -> ok.
parse_and_publish(Dataset, Product, Flow, Body) ->
    try
        D       = jsx:decode(Body, [return_maps]),
        Data    = maps:get(<<"data">>, D, []),
        case Data of
            [] -> ok;
            [Latest | _] ->
                Value  = maps:get(<<"value">>,  Latest, null),
                Period = maps:get(<<"time">>,   Latest, null),
                Key    = list_to_binary(Dataset ++ "." ++ Product ++ "." ++ Flow),
                Payload = #{
                    dataset => list_to_binary(Dataset),
                    product => list_to_binary(Product),
                    flow    => list_to_binary(Flow),
                    value   => Value,
                    period  => Period
                },
                ets_cache:put({fundamental, Key}, Payload),
                data_router:publish(#{
                    type      => fundamental,
                    source    => iea,
                    symbol    => Key,
                    timestamp => erlang:system_time(millisecond),
                    payload   => Payload
                })
        end
    catch C:E ->
        lager:error("IEA parse error ~s: ~p:~p", [Dataset, C, E])
    end.
