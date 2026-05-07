%% @doc OTP application callback for the Energy Gateway.
%%
%% Starts the root supervisor and Cowboy WebSocket listener on the
%% configured port.  All child processes are described in
%% {@link energy_gateway_sup}.
%%
%% @author Energy Terminal Project
%% @copyright 2024
-module(energy_gateway_app).
-behaviour(application).

-export([start/2, stop/1]).

%%-----------------------------------------------------------------------------
%% Application callbacks
%%-----------------------------------------------------------------------------

%% @doc Start the application.
%%
%% Initialises the Cowboy HTTP/WebSocket listener and launches the root
%% supervisor tree.
%%
%% @param StartType  OTP start type atom (normal | {takeover, _} | {failover, _}).
%% @param StartArgs  Reserved; unused.
%% @returns `{ok, Pid}' on success, `{error, Reason}' on failure.
-spec start(StartType :: application:start_type(), StartArgs :: term()) ->
    {ok, pid()} | {error, term()}.
start(_StartType, _StartArgs) ->
    Port    = application:get_env(energy_gateway, ws_port, 8765),
    Dispatch = cowboy_router:compile([
        {'_', [
            {"/ws",     ws_handler, []},
            {"/health", health_handler, []}
        ]}
    ]),
    {ok, _} = cowboy:start_clear(http_listener,
        [{port, Port}],
        #{env => #{dispatch => Dispatch}}
    ),
    lager:info("Energy Gateway WebSocket listening on port ~p", [Port]),
    energy_gateway_sup:start_link().

%% @doc Stop the application.
%%
%% @param _State  Ignored.
%% @returns `ok'.
-spec stop(State :: term()) -> ok.
stop(_State) ->
    cowboy:stop_listener(http_listener),
    ok.
