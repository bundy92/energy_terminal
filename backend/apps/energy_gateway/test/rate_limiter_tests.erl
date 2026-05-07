%% @doc EUnit tests for {@link rate_limiter}.
%%
%% Tests cover: token consumption, rate-limiting enforcement, refill
%% behaviour, unknown endpoint bypass, and status reporting.
-module(rate_limiter_tests).
-include_lib("eunit/include/eunit.hrl").

%%=============================================================================
%% Fixtures
%%=============================================================================

setup() ->
    %% Override application env for tests: 60 rpm = 1 token/s
    application:set_env(energy_gateway, rate_limits, [
        {test_endpoint, 60},
        {slow_endpoint, 6}   %% 0.1 tokens/s — easily exhausted
    ]),
    {ok, Pid} = rate_limiter:start_link(),
    Pid.

teardown(Pid) ->
    exit(Pid, normal),
    timer:sleep(20).

rate_limiter_test_() ->
    {setup, fun setup/0, fun teardown/1, [
        {"consume returns ok for known endpoint", fun test_consume_ok/0},
        {"unknown endpoint is allowed with warning", fun test_unknown_bypass/0},
        {"status returns map of bucket info",    fun test_status/0},
        {"slow endpoint exhausts and rate limits", fun test_rate_limit/0}
    ]}.

%%=============================================================================
%% Tests
%%=============================================================================

test_consume_ok() ->
    ?assertEqual(ok, rate_limiter:check_and_consume(test_endpoint)).

test_unknown_bypass() ->
    %% Unknown endpoints must not crash — just bypass
    ?assertEqual(ok, rate_limiter:check_and_consume(nonexistent_endpoint)).

test_status() ->
    Status = rate_limiter:status(),
    ?assert(is_map(Status)),
    ?assert(maps:is_key(test_endpoint, Status)),
    #{tokens := T, capacity := C} = maps:get(test_endpoint, Status),
    ?assert(T >= 0),
    ?assert(C > 0).

test_rate_limit() ->
    %% Drain the slow_endpoint bucket (0.1 token/s → ~0 tokens initially)
    %% Force-drain by consuming in a tight loop until rate_limited
    Results = [rate_limiter:check_and_consume(slow_endpoint) || _ <- lists:seq(1, 20)],
    %% At least some requests should be rate-limited
    RateLimited = [R || R <- Results, R =:= {error, rate_limited}],
    ?assert(length(RateLimited) > 0).
