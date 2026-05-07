%% @doc Pub/sub data router.
%%
%% Feed GenServers publish normalised `tick' and `fundamental' messages
%% here.  WebSocket handler processes subscribe on connection and receive
%% every subsequent publish via Erlang message delivery.
%%
%% == Message format published to subscribers ==
%%
%% ```
%% {data_event, #{
%%     type      => tick | fundamental | weather | macro,
%%     source    => yahoo_finance | eia | open_meteo | fred | iea,
%%     symbol    => binary(),
%%     timestamp => integer(),   %% Unix epoch ms
%%     payload   => map()
%% }}
%% '''
-module(data_router).
-behaviour(gen_server).

-export([start_link/0, subscribe/0, unsubscribe/0, publish/1, subscriber_count/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER, ?MODULE).

-record(state, {
    subscribers :: sets:set(pid())
}).

%%=============================================================================
%% Public API
%%=============================================================================

%% @doc Start the router process.
-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

%% @doc Subscribe the calling process to all data events.
%%
%% The subscriber receives `{data_event, EventMap}' messages.
%% A monitor is set so the subscription is cleaned up on crash/exit.
%%
%% @returns `ok'.
-spec subscribe() -> ok.
subscribe() ->
    gen_server:call(?SERVER, {subscribe, self()}).

%% @doc Remove the calling process from the subscriber list.
%%
%% @returns `ok'.
-spec unsubscribe() -> ok.
unsubscribe() ->
    gen_server:call(?SERVER, {unsubscribe, self()}).

%% @doc Publish a data event to all current subscribers.
%%
%% @param Event  Map conforming to the event schema (see module doc).
%% @returns `ok'.
-spec publish(Event :: map()) -> ok.
publish(Event) ->
    gen_server:cast(?SERVER, {publish, Event}).

%% @doc Return the number of active WebSocket subscribers.
%%
%% @returns Non-negative integer.
-spec subscriber_count() -> non_neg_integer().
subscriber_count() ->
    gen_server:call(?SERVER, subscriber_count).

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init([]) -> {ok, #state{}}.
init([]) ->
    {ok, #state{subscribers = sets:new()}}.

handle_call({subscribe, Pid}, _From, #state{subscribers = Subs} = S) ->
    erlang:monitor(process, Pid),
    {reply, ok, S#state{subscribers = sets:add_element(Pid, Subs)}};

handle_call({unsubscribe, Pid}, _From, #state{subscribers = Subs} = S) ->
    {reply, ok, S#state{subscribers = sets:del_element(Pid, Subs)}};

handle_call(subscriber_count, _From, #state{subscribers = Subs} = S) ->
    {reply, sets:size(Subs), S};

handle_call(_Req, _From, State) ->
    {reply, ok, State}.

handle_cast({publish, Event}, #state{subscribers = Subs} = S) ->
    sets:fold(fun(Pid, _) -> Pid ! {data_event, Event} end, ok, Subs),
    {noreply, S};

handle_cast(_Msg, State) ->
    {noreply, State}.

%% Clean up dead subscriber
handle_info({'DOWN', _Ref, process, Pid, _Reason},
            #state{subscribers = Subs} = S) ->
    {noreply, S#state{subscribers = sets:del_element(Pid, Subs)}};

handle_info(_Info, State) ->
    {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.
