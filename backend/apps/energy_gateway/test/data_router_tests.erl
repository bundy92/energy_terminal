%% @doc EUnit tests for {@link data_router}.
%%
%% Tests cover: subscribe/publish/unsubscribe lifecycle, multi-subscriber
%% fan-out, dead-subscriber cleanup via monitor, and subscriber_count.
-module(data_router_tests).
-include_lib("eunit/include/eunit.hrl").

setup() ->
    {ok, Pid} = data_router:start_link(),
    Pid.

teardown(Pid) ->
    exit(Pid, normal),
    timer:sleep(10).

router_test_() ->
    {setup, fun setup/0, fun teardown/1, [
        {"subscribe increments count",      fun test_subscribe_count/0},
        {"publish delivers to subscriber",  fun test_publish_delivers/0},
        {"unsubscribe stops delivery",      fun test_unsubscribe/0},
        {"multi-subscriber fan-out",        fun test_fanout/0},
        {"dead subscriber auto-removed",    fun test_dead_subscriber/0}
    ]}.

test_subscribe_count() ->
    ?assertEqual(0, data_router:subscriber_count()),
    data_router:subscribe(),
    ?assertEqual(1, data_router:subscriber_count()),
    data_router:unsubscribe(),
    ?assertEqual(0, data_router:subscriber_count()).

test_publish_delivers() ->
    data_router:subscribe(),
    Event = #{type => tick, symbol => <<"CL=F">>, payload => #{}},
    data_router:publish(Event),
    receive
        {data_event, Received} ->
            ?assertEqual(Event, Received)
    after 1000 ->
        ?assert(false)
    end,
    data_router:unsubscribe().

test_unsubscribe() ->
    data_router:subscribe(),
    data_router:unsubscribe(),
    data_router:publish(#{type => tick}),
    receive
        {data_event, _} -> ?assert(false)
    after 200 -> ok
    end.

test_fanout() ->
    Parent = self(),
    Pids   = [spawn(fun() ->
                data_router:subscribe(),
                Parent ! {ready, self()},
                receive {data_event, _} -> Parent ! {got_event, self()} end
              end) || _ <- lists:seq(1, 3)],
    %% Wait for all to subscribe
    [receive {ready, P} -> ok after 500 -> error(timeout) end || P <- Pids],
    data_router:publish(#{type => macro, symbol => <<"TEST">>}),
    [receive {got_event, P} -> ok after 500 -> error({timeout, P}) end || P <- Pids].

test_dead_subscriber() ->
    Pid = spawn(fun() ->
        data_router:subscribe(),
        timer:sleep(50)
    end),
    timer:sleep(100),   %% let it die
    ?assertEqual(0, data_router:subscriber_count()),
    _ = Pid.
