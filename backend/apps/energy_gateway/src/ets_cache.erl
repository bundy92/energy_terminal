%% @doc ETS-backed in-memory cache with TTL eviction.
%%
%% Owns the ETS tables so that they survive feed-server crashes.  All
%% feed GenServers write through this process; readers query ETS directly
%% (no message-passing overhead for reads).
%%
%% == Table layout ==
%%
%% `energy_cache':
%%   `{Key, Value, InsertedAt}' where InsertedAt is `erlang:monotonic_time(second)'.
%%
%% == Usage ==
%%
%% ```
%% ok  = ets_cache:put(<<"CL=F">>, #{close => 85.23}),
%% {ok, Data}   = ets_cache:get(<<"CL=F">>),
%% not_found    = ets_cache:get(<<"NONEXISTENT">>),
%% stale        = ets_cache:get_fresh(<<"CL=F">>, 60).
%% '''
-module(ets_cache).
-behaviour(gen_server).

%% Public API
-export([start_link/0, put/2, get/1, get_fresh/2, delete/1, keys/0, flush/0]).
%% GenServer callbacks
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(TABLE,  energy_cache).
-define(SERVER, ?MODULE).

%%=============================================================================
%% Public API
%%=============================================================================

%% @doc Start the cache process and create ETS tables.
-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

%% @doc Insert or replace a value in the cache.
%%
%% @param Key    Arbitrary term used as lookup key.
%% @param Value  Arbitrary term to store.
%% @returns `ok'.
-spec put(Key :: term(), Value :: term()) -> ok.
put(Key, Value) ->
    Now = erlang:monotonic_time(second),
    true = ets:insert(?TABLE, {Key, Value, Now}),
    ok.

%% @doc Retrieve a value from the cache (no TTL check).
%%
%% @param Key  Lookup key.
%% @returns `{ok, Value}' | `not_found'.
-spec get(Key :: term()) -> {ok, term()} | not_found.
get(Key) ->
    case ets:lookup(?TABLE, Key) of
        [{_K, Value, _Ts}] -> {ok, Value};
        []                 -> not_found
    end.

%% @doc Retrieve a value only if it was inserted within `MaxAgeSecs' seconds.
%%
%% @param Key         Lookup key.
%% @param MaxAgeSecs  Maximum acceptable age in seconds.
%% @returns `{ok, Value}' | `not_found' | `stale'.
-spec get_fresh(Key :: term(), MaxAgeSecs :: non_neg_integer()) ->
    {ok, term()} | not_found | stale.
get_fresh(Key, MaxAgeSecs) ->
    Now = erlang:monotonic_time(second),
    case ets:lookup(?TABLE, Key) of
        [{_K, Value, Ts}] when (Now - Ts) =< MaxAgeSecs -> {ok, Value};
        [{_K, _V,   _Ts}]                                -> stale;
        []                                               -> not_found
    end.

%% @doc Delete a key from the cache.
%%
%% @param Key  Key to remove.
%% @returns `ok'.
-spec delete(Key :: term()) -> ok.
delete(Key) ->
    true = ets:delete(?TABLE, Key),
    ok.

%% @doc Return all keys currently in the cache.
%%
%% @returns List of keys.
-spec keys() -> [term()].
keys() ->
    ets:select(?TABLE, [{ {'$1', '_', '_'}, [], ['$1'] }]).

%% @doc Remove all entries from the cache.
%%
%% @returns `ok'.
-spec flush() -> ok.
flush() ->
    true = ets:delete_all_objects(?TABLE),
    ok.

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init(Args :: term()) -> {ok, #{}}.
init(_Args) ->
    ets:new(?TABLE, [named_table, public, set,
                     {read_concurrency, true},
                     {write_concurrency, true}]),
    lager:info("ETS cache initialised (~p)", [?TABLE]),
    {ok, #{}}.

handle_call(_Request, _From, State) -> {reply, ok, State}.
handle_cast(_Msg,            State) -> {noreply, State}.
handle_info(_Info,           State) -> {noreply, State}.
terminate(_Reason,           _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.
