%% @doc EUnit tests for {@link market_feed_server}.
%%
%% Uses `meck' to mock `hackney' and `rate_limiter' so no real HTTP
%% calls are made.  Tests verify that the feed correctly parses Yahoo
%% Finance JSON responses, writes to ETS cache, and publishes events
%% through the data router.
-module(market_feed_server_tests).
-include_lib("eunit/include/eunit.hrl").

-define(SYMBOL, <<"CL=F">>).

%% Sample Yahoo Finance v7 quote JSON (minimal fields)
-define(QUOTE_JSON, <<"{\"quoteResponse\":{\"result\":[{
    \"symbol\": \"CL=F\",
    \"regularMarketPrice\": 85.5,
    \"regularMarketOpen\": 84.0,
    \"regularMarketDayHigh\": 86.2,
    \"regularMarketDayLow\": 83.8,
    \"regularMarketVolume\": 150000,
    \"regularMarketChange\": 1.5,
    \"regularMarketChangePercent\": 1.79
}],\"error\":null}}">>).

%%=============================================================================
%% Fixtures
%%=============================================================================

setup() ->
    %% Start dependencies
    {ok, Cache}  = ets_cache:start_link(),
    {ok, Router} = data_router:start_link(),

    %% Mock hackney to return our fixture JSON
    meck:new(hackney, [passthrough]),
    meck:expect(hackney, get, fun(_Url, _Headers, _Body, _Opts) ->
        {ok, 200, [], ?QUOTE_JSON}
    end),

    %% Mock rate_limiter to always allow
    meck:new(rate_limiter, [passthrough]),
    meck:expect(rate_limiter, check_and_consume, fun(_) -> ok end),

    application:set_env(energy_gateway, poll_interval_ms, 999_999),
    application:set_env(energy_gateway, instruments, [?SYMBOL]),

    {ok, Feed} = market_feed_server:start_link(),
    {Cache, Router, Feed}.

teardown({Cache, Router, Feed}) ->
    exit(Feed,   normal),
    exit(Router, normal),
    exit(Cache,  normal),
    meck:unload(hackney),
    meck:unload(rate_limiter),
    timer:sleep(20).

feed_test_() ->
    {setup, fun setup/0, fun teardown/1, [
        {"force_poll writes tick to ETS cache",  fun test_poll_writes_cache/0},
        {"force_poll publishes router event",    fun test_poll_publishes_event/0},
        {"last_tick returns cached value",       fun test_last_tick/0}
    ]}.

%%=============================================================================
%% Tests
%%=============================================================================

test_poll_writes_cache() ->
    market_feed_server:force_poll(),
    timer:sleep(100),
    Result = ets_cache:get({tick, ?SYMBOL}),
    ?assertMatch({ok, #{close := 85.5}}, Result).

test_poll_publishes_event() ->
    data_router:subscribe(),
    market_feed_server:force_poll(),
    receive
        {data_event, #{type := tick, symbol := ?SYMBOL}} -> ok
    after 1000 ->
        ?assert(false)
    end,
    data_router:unsubscribe().

test_last_tick() ->
    market_feed_server:force_poll(),
    timer:sleep(100),
    ?assertMatch({ok, #{symbol := ?SYMBOL, close := 85.5}},
                 market_feed_server:last_tick(?SYMBOL)).
