%% @doc Token-bucket rate limiter for outbound API calls.
%%
%% Each registered endpoint has its own bucket refilled at a configured
%% rate (requests per minute).  Callers invoke `check_and_consume/1'
%% before every HTTP request; the call blocks (up to `?MAX_WAIT_MS') if
%% the bucket is temporarily empty.
%%
%% == Configuration ==
%%
%% Rates are read from `sys.config' under the key:
%% ```
%% {rate_limits, [{yahoo_finance, 60}, {eia, 60}, ...]}
%% '''
%%
%% == Example ==
%%
%% ```
%% ok    = rate_limiter:check_and_consume(yahoo_finance),
%% %% ... make HTTP request ...
%% '''
-module(rate_limiter).
-behaviour(gen_server).

-export([start_link/0, check_and_consume/1, status/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(SERVER,      ?MODULE).
-define(MAX_WAIT_MS, 5000).
-define(REFILL_TICK, 1000).   %% Refill every 1 s; rate in req/min ÷ 60

-record(bucket, {
    tokens    :: float(),
    capacity  :: float(),
    rate_ps   :: float()   %% tokens per second
}).

%%=============================================================================
%% Public API
%%=============================================================================

%% @doc Start the rate limiter process.
-spec start_link() -> gen_server:start_ret().
start_link() ->
    gen_server:start_link({local, ?SERVER}, ?MODULE, [], []).

%% @doc Consume one token from the named endpoint's bucket.
%%
%% Blocks up to `?MAX_WAIT_MS' ms if the bucket is empty.
%%
%% @param Endpoint  Atom identifying the API endpoint (e.g. `yahoo_finance').
%% @returns `ok' | `{error, rate_limited}'.
-spec check_and_consume(Endpoint :: atom()) -> ok | {error, rate_limited}.
check_and_consume(Endpoint) ->
    gen_server:call(?SERVER, {consume, Endpoint}, ?MAX_WAIT_MS).

%% @doc Return a map of all bucket states for monitoring.
%%
%% @returns Map of `Endpoint => #{tokens, capacity, rate_ps}'.
-spec status() -> map().
status() ->
    gen_server:call(?SERVER, status).

%%=============================================================================
%% GenServer callbacks
%%=============================================================================

-spec init([]) -> {ok, map()}.
init([]) ->
    Rates    = application:get_env(energy_gateway, rate_limits, []),
    Buckets  = maps:from_list([
        begin
            RatePS = RPM / 60.0,
            {Ep, #bucket{tokens = RPM / 60.0, capacity = RPM / 60.0, rate_ps = RatePS}}
        end
        || {Ep, RPM} <- Rates
    ]),
    erlang:send_after(?REFILL_TICK, self(), refill),
    lager:info("Rate limiter initialised for ~p endpoints", [maps:size(Buckets)]),
    {ok, Buckets}.

handle_call({consume, Endpoint}, _From, Buckets) ->
    case maps:get(Endpoint, Buckets, undefined) of
        undefined ->
            %% Unknown endpoint — allow but warn
            lager:warning("Unknown endpoint ~p, bypassing rate limit", [Endpoint]),
            {reply, ok, Buckets};
        #bucket{tokens = T} = B when T >= 1.0 ->
            {reply, ok, Buckets#{Endpoint => B#bucket{tokens = T - 1.0}}};
        #bucket{} ->
            {reply, {error, rate_limited}, Buckets}
    end;

handle_call(status, _From, Buckets) ->
    Summary = maps:map(fun(_K, #bucket{tokens = T, capacity = C, rate_ps = R}) ->
        #{tokens => T, capacity => C, rate_ps => R}
    end, Buckets),
    {reply, Summary, Buckets};

handle_call(_Req, _From, State) ->
    {reply, ok, State}.

handle_cast(_Msg, State) -> {noreply, State}.

handle_info(refill, Buckets) ->
    DeltaSecs = ?REFILL_TICK / 1000.0,
    Refilled  = maps:map(fun(_K, #bucket{tokens = T, capacity = C, rate_ps = R} = B) ->
        B#bucket{tokens = min(C, T + R * DeltaSecs)}
    end, Buckets),
    erlang:send_after(?REFILL_TICK, self(), refill),
    {noreply, Refilled};

handle_info(_Info, State) -> {noreply, State}.

terminate(_Reason, _State) -> ok.
code_change(_OldVsn, State, _Extra) -> {ok, State}.
