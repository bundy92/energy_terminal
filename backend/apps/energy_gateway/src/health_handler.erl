%% @doc Minimal HTTP health-check endpoint.
%%
%% Returns `200 OK' with a JSON body summarising system status.
%% Consumed by load-balancers, Docker health checks, and monitoring
%% dashboards.
%%
%% == Response ==
%%
%% ```
%% GET /health
%% {
%%   "status":      "ok",
%%   "subscribers": 3,
%%   "cache_keys":  142,
%%   "uptime_s":    3600
%% }
%% '''
-module(health_handler).

-export([init/2]).

-spec init(Req :: cowboy_req:req(), State :: any()) ->
    {ok, cowboy_req:req(), any()}.
init(Req, State) ->
    Body = jsx:encode(#{
        status      => <<"ok">>,
        subscribers => data_router:subscriber_count(),
        cache_keys  => length(ets_cache:keys()),
        uptime_s    => erlang:monotonic_time(second)
    }),
    Resp = cowboy_req:reply(200,
        #{<<"content-type">> => <<"application/json">>},
        Body, Req),
    {ok, Resp, State}.
