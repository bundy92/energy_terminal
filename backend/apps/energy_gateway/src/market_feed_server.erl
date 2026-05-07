%% @doc Yahoo Finance feed GenServer.
%%
%% Periodically fetches OHLCV quote data for the configured instrument
%% list via the Yahoo Finance v8 quote endpoint.  Results are normalised
%% into the internal tick schema, written to `ets_cache', and published
%% through `data_router'.
%%
%% == Instrument configuration ==
%%
%% Symbols are read from `sys.config':
%% ```
%% {instruments, [<<"CL=F">>, <<"NG=F">>, ...]}
%% '''
%%
%% == Internal tick schema ==
%%
%% ```
%% #{
%%     symbol    => binary(),
%%     open      => float(),
%%     high      => float(),
%%     low       => float(),
%%     close     => float(),
%%     volume    => integer(),
%%     change    => float(),
%%     change_pct=> float(),
%%     timestamp => integer()   %% Unix epoch ms
%% }
%% '''
-module(market_feed_server).
-behaviour(gen_server).

-export([start_link/0, force_poll/0, last_tick/1]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,       ?MODULE).
-define(BASE_URL,     "https://query1.finance.yahoo.com/v8/finance/spark").
-define(QUOTE_URL,    "https://query1.finance.yahoo.com/v7/finance/quote").
-define(ENDPOINT,     yahoo_finance).

%%=============================================================================
%% Public API
%%=============================================================================

%% @doc Start the Yahoo Finance feed GenServer.
-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

%% @doc Force an immediate poll outside the regular schedule.
%% @returns `ok'.
-spec force_poll() -> ok.
force_poll() ->
    gen_server:cast(?SERVER, poll).

%% @doc Return the most recent tick for a symbol from the local cache.
%%
%% @param Symbol  Binary ticker (e.g. `<<"CL=F">>').
%% @returns `{ok, TickMap}' | `not_found'.
-spec last_tick(Symbol :: binary()) -> {ok, map()} | not_found.
last_tick(Symbol) ->
    ets_cache:get({tick, Symbol}).

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init([]) -> {ok, map()}.
init([]) ->
    Interval    = application:get_env(energy_gateway, poll_interval_ms, 30_000),
    Instruments = application:get_env(energy_gateway, instruments, []),
    erlang:send_after(500, self(), poll),
    lager:info("Market feed server started, ~p instruments, interval ~p ms",
               [length(Instruments), Interval]),
    {ok, #{interval => Interval, instruments => Instruments}}.

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
do_poll(#{instruments := []}) ->
    lager:warning("No instruments configured for Yahoo Finance feed"),
    ok;
do_poll(#{instruments := Instruments}) ->
    case rate_limiter:check_and_consume(?ENDPOINT) of
        ok ->
            Symbols    = binary_join(Instruments, <<",">>),
            Url        = <<?QUOTE_URL, "?symbols=", Symbols/binary,
                           "&fields=regularMarketPrice,regularMarketOpen,",
                           "regularMarketDayHigh,regularMarketDayLow,",
                           "regularMarketVolume,regularMarketChange,",
                           "regularMarketChangePercent">>,
            fetch_and_publish(binary_to_list(Url));
        {error, rate_limited} ->
            lager:warning("Yahoo Finance rate limit hit, skipping poll")
    end.

-spec fetch_and_publish(Url :: string()) -> ok.
fetch_and_publish(Url) ->
    Headers = [{"User-Agent", "energy-terminal/0.1"}],
    case hackney:get(Url, Headers, <<>>, [with_body]) of
        {ok, 200, _Headers, Body} ->
            process_response(Body);
        {ok, Status, _, _} ->
            lager:warning("Yahoo Finance returned HTTP ~p", [Status]);
        {error, Reason} ->
            lager:error("Yahoo Finance fetch error: ~p", [Reason])
    end.

-spec process_response(Body :: binary()) -> ok.
process_response(Body) ->
    try
        #{<<"quoteResponse">> := #{<<"result">> := Results}} = jsx:decode(Body, [return_maps]),
        Ts = erlang:system_time(millisecond),
        lists:foreach(fun(R) -> process_quote(R, Ts) end, Results)
    catch
        C:E:ST ->
            lager:error("Yahoo Finance parse error ~p:~p ~p", [C, E, ST])
    end.

-spec process_quote(Quote :: map(), Ts :: integer()) -> ok.
process_quote(Quote, Ts) ->
    Symbol = maps:get(<<"symbol">>, Quote, undefined),
    Tick   = #{
        symbol     => Symbol,
        open       => maps:get(<<"regularMarketOpen">>,          Quote, 0.0),
        high       => maps:get(<<"regularMarketDayHigh">>,       Quote, 0.0),
        low        => maps:get(<<"regularMarketDayLow">>,        Quote, 0.0),
        close      => maps:get(<<"regularMarketPrice">>,         Quote, 0.0),
        volume     => maps:get(<<"regularMarketVolume">>,        Quote, 0),
        change     => maps:get(<<"regularMarketChange">>,        Quote, 0.0),
        change_pct => maps:get(<<"regularMarketChangePercent">>, Quote, 0.0),
        timestamp  => Ts
    },
    ets_cache:put({tick, Symbol}, Tick),
    data_router:publish(#{
        type      => tick,
        source    => yahoo_finance,
        symbol    => Symbol,
        timestamp => Ts,
        payload   => Tick
    }).

-spec binary_join([binary()], binary()) -> binary().
binary_join([], _Sep)      -> <<>>;
binary_join([H | T], Sep)  ->
    lists:foldl(fun(B, Acc) -> <<Acc/binary, Sep/binary, B/binary>> end, H, T).
