%% @doc Root supervisor for the Energy Gateway application.
%%
%% Manages the following child processes under a `one_for_one' strategy so
%% that a crash in any single feed does not bring down the rest of the
%% system:
%%
%% <ol>
%%   <li>`ets_cache'          — shared in-memory cache (ETS owner process)</li>
%%   <li>`rate_limiter'       — token-bucket rate limiter for all APIs</li>
%%   <li>`feed_registry'      — named process registry for feed GenServers</li>
%%   <li>`data_router'        — pub/sub fan-out to WebSocket subscribers</li>
%%   <li>`market_feed_server' — Yahoo Finance poller</li>
%%   <li>`eia_feed_server'    — US EIA weekly data poller</li>
%%   <li>`weather_feed_server'— Open-Meteo weather / HDD-CDD poller</li>
%%   <li>`fred_feed_server'   — Federal Reserve FRED macro poller</li>
%% </ol>
%%
%% IEA feed is started conditionally if `iea' appears in the
%% `feeds_enabled' configuration list.
-module(energy_gateway_sup).
-behaviour(supervisor).

-export([start_link/0]).
-export([init/1]).

-define(SERVER, ?MODULE).

%%-----------------------------------------------------------------------------
%% Public API
%%-----------------------------------------------------------------------------

%% @doc Start the root supervisor.
%% @returns `{ok, Pid}' | `{error, Reason}'.
-spec start_link() -> supervisor:startlink_ret().
start_link() ->
    supervisor:start_link({local, ?SERVER}, ?MODULE, []).

%%-----------------------------------------------------------------------------
%% Supervisor callback
%%-----------------------------------------------------------------------------

%% @doc Initialise the supervision tree.
%% @param _Args  Ignored.
%% @returns Supervisor child specification.
-spec init(Args :: term()) ->
    {ok, {supervisor:sup_flags(), [supervisor:child_spec()]}}.
init(_Args) ->
    SupFlags = #{
        strategy  => one_for_one,
        intensity => 5,
        period    => 10
    },

    EnabledFeeds = application:get_env(energy_gateway, feeds_enabled,
                                       [yahoo_finance, eia, open_meteo, fred]),

    BaseChildren = [
        child(ets_cache,           ets_cache,           worker),
        child(rate_limiter,        rate_limiter,         worker),
        child(feed_registry,       feed_registry,        worker),
        child(data_router,         data_router,          worker),
        child(market_feed_server,  market_feed_server,   worker),
        child(eia_feed_server,     eia_feed_server,      worker),
        child(weather_feed_server, weather_feed_server,  worker),
        child(fred_feed_server,    fred_feed_server,     worker)
    ],

    IEAChild = case lists:member(iea, EnabledFeeds) of
        true  -> [child(iea_feed_server, iea_feed_server, worker)];
        false -> []
    end,

    {ok, {SupFlags, BaseChildren ++ IEAChild}}.

%%-----------------------------------------------------------------------------
%% Internal helpers
%%-----------------------------------------------------------------------------

-spec child(Id, Module, Type) -> supervisor:child_spec() when
    Id     :: atom(),
    Module :: module(),
    Type   :: worker | supervisor.
child(Id, Module, Type) ->
    #{
        id       => Id,
        start    => {Module, start_link, []},
        restart  => permanent,
        shutdown => 5000,
        type     => Type,
        modules  => [Module]
    }.
