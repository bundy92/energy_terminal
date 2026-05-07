%% @doc EUnit tests for {@link ets_cache}.
%%
%% Tests cover: put/get round-trip, TTL-based freshness, stale detection,
%% key deletion, flush, and concurrent write safety.
-module(ets_cache_tests).
-include_lib("eunit/include/eunit.hrl").

%%=============================================================================
%% Test fixtures
%%=============================================================================

setup() ->
    %% Start the cache process which creates the ETS table
    {ok, Pid} = ets_cache:start_link(),
    Pid.

teardown(Pid) ->
    ets_cache:flush(),
    exit(Pid, normal),
    timer:sleep(10).

cache_test_() ->
    {setup, fun setup/0, fun teardown/1, [
        {"put and get round-trip",         fun test_put_get/0},
        {"get returns not_found for miss", fun test_get_miss/0},
        {"get_fresh returns ok within TTL",fun test_get_fresh_ok/0},
        {"get_fresh returns stale",        fun test_get_fresh_stale/0},
        {"delete removes entry",           fun test_delete/0},
        {"flush clears all entries",       fun test_flush/0},
        {"keys returns all stored keys",   fun test_keys/0},
        {"overwrite updates value",        fun test_overwrite/0}
    ]}.

%%=============================================================================
%% Individual tests
%%=============================================================================

test_put_get() ->
    ok = ets_cache:put(<<"CL=F">>, #{close => 85.50}),
    ?assertMatch({ok, #{close := 85.50}}, ets_cache:get(<<"CL=F">>)).

test_get_miss() ->
    ?assertEqual(not_found, ets_cache:get(<<"NONEXISTENT">>)).

test_get_fresh_ok() ->
    ok = ets_cache:put(fresh_key, <<"fresh_value">>),
    ?assertMatch({ok, <<"fresh_value">>}, ets_cache:get_fresh(fresh_key, 60)).

test_get_fresh_stale() ->
    %% Manually insert with a very old timestamp via ets directly
    Now = erlang:monotonic_time(second),
    ets:insert(energy_cache, {stale_key, <<"old_value">>, Now - 120}),
    ?assertEqual(stale, ets_cache:get_fresh(stale_key, 60)).

test_delete() ->
    ok = ets_cache:put(delete_me, 42),
    ok = ets_cache:delete(delete_me),
    ?assertEqual(not_found, ets_cache:get(delete_me)).

test_flush() ->
    ok = ets_cache:put(a, 1),
    ok = ets_cache:put(b, 2),
    ok = ets_cache:flush(),
    ?assertEqual([], ets_cache:keys()).

test_keys() ->
    ets_cache:flush(),
    ok = ets_cache:put(k1, v1),
    ok = ets_cache:put(k2, v2),
    Keys = lists:sort(ets_cache:keys()),
    ?assertEqual([k1, k2], Keys).

test_overwrite() ->
    ok = ets_cache:put(overwrite_key, <<"original">>),
    ok = ets_cache:put(overwrite_key, <<"updated">>),
    ?assertMatch({ok, <<"updated">>}, ets_cache:get(overwrite_key)).
