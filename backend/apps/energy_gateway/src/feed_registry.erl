%% @doc Named process registry for feed GenServers.
%%
%% Provides a lightweight lookup table mapping feed atom names to their
%% registered PIDs.  This allows the WebSocket handler and health endpoint
%% to interrogate feed liveness without knowing process names directly.
%%
%% == Registered feed names ==
%%
%% <ul>
%%   <li>`market_feed_server'</li>
%%   <li>`eia_feed_server'</li>
%%   <li>`weather_feed_server'</li>
%%   <li>`fred_feed_server'</li>
%%   <li>`iea_feed_server' (optional)</li>
%% </ul>
%%
%% == Usage ==
%%
%% ```
%% {ok, Pid}    = feed_registry:lookup(market_feed_server),
%% ok           = feed_registry:force_poll(market_feed_server).
%% '''
-module(feed_registry).
-behaviour(gen_server).

-export([start_link/0, lookup/1, all/0, force_poll/1]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER, ?MODULE).

-define(FEEDS, [
    market_feed_server,
    eia_feed_server,
    weather_feed_server,
    fred_feed_server
]).

%%=============================================================================
%% Public API
%%=============================================================================

%% @doc Start the feed registry.
-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

%% @doc Look up the PID of a named feed.
%%
%% @param Feed  Atom name of the feed GenServer.
%% @returns `{ok, Pid}' | `{error, not_found}'.
-spec lookup(Feed :: atom()) -> {ok, pid()} | {error, not_found}.
lookup(Feed) ->
    gen_server:call(?SERVER, {lookup, Feed}).

%% @doc Return status of all registered feeds.
%%
%% @returns List of `{FeedName, alive | dead}' tuples.
-spec all() -> [{atom(), alive | dead}].
all() ->
    gen_server:call(?SERVER, all).

%% @doc Send a `force_poll' cast to a named feed.
%%
%% @param Feed  Atom name of the feed GenServer.
%% @returns `ok' | `{error, not_found}'.
-spec force_poll(Feed :: atom()) -> ok | {error, not_found}.
force_poll(Feed) ->
    gen_server:call(?SERVER, {force_poll, Feed}).

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init([]) -> {ok, #{}}.
init([]) ->
    %% Delay registration slightly to allow supervised children to start
    erlang:send_after(2000, self(), register_feeds),
    {ok, #{}}.

handle_call({lookup, Feed}, _From, State) ->
    case maps:get(Feed, State, undefined) of
        undefined -> {reply, {error, not_found}, State};
        Pid       -> {reply, {ok, Pid}, State}
    end;

handle_call(all, _From, State) ->
    Status = maps:fold(fun(Name, Pid, Acc) ->
        Alive = case is_process_alive(Pid) of
            true  -> alive;
            false -> dead
        end,
        [{Name, Alive} | Acc]
    end, [], State),
    {reply, Status, State};

handle_call({force_poll, Feed}, _From, State) ->
    case maps:get(Feed, State, undefined) of
        undefined -> {reply, {error, not_found}, State};
        _Pid      ->
            gen_server:cast(Feed, poll),
            {reply, ok, State}
    end;

handle_call(_Req, _From, State) ->
    {reply, ok, State}.

handle_cast(_Msg, State) -> {noreply, State}.

handle_info(register_feeds, _State) ->
    Registered = maps:from_list([
        {Feed, whereis(Feed)}
        || Feed <- ?FEEDS,
           whereis(Feed) =/= undefined
    ]),
    lager:info("Feed registry: registered ~p feeds",
               [maps:size(Registered)]),
    {noreply, Registered};

handle_info(_Info, State) -> {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.
