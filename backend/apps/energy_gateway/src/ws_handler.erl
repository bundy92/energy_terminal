%% @doc Cowboy WebSocket handler for the Python desktop client.
%%
%% Each WebSocket connection maps to one handler process.  On upgrade the
%% handler subscribes to `data_router'; every published `data_event' is
%% JSON-encoded and forwarded to the client.
%%
%% == Client→Server commands ==
%%
%% ```
%% {"cmd": "subscribe",   "symbols": ["CL=F", "NG=F"]}
%% {"cmd": "unsubscribe", "symbols": ["CL=F"]}
%% {"cmd": "get_cache",   "key": "tick:CL=F"}
%% {"cmd": "ping"}
%% '''
%%
%% == Server→Client envelope ==
%%
%% ```
%% {
%%   "type":      "tick" | "fundamental" | "weather" | "macro" | "pong" | "error",
%%   "source":    "yahoo_finance" | ...,
%%   "symbol":    "CL=F",
%%   "timestamp": 1710000000000,
%%   "payload":   { ... }
%% }
%% '''
-module(ws_handler).
-behaviour(cowboy_websocket).

-export([init/2, websocket_init/1, websocket_handle/2,
         websocket_info/2, terminate/3]).

%%=============================================================================
%% Cowboy callbacks
%%=============================================================================

-spec init(Req :: cowboy_req:req(), Opts :: any()) ->
    {cowboy_websocket, cowboy_req:req(), map()}.
init(Req, Opts) ->
    {cowboy_websocket, Req, #{opts => Opts}, #{idle_timeout => 60_000}}.

-spec websocket_init(State :: map()) ->
    {ok, map()} | {reply, cowboy_websocket:frame(), map()}.
websocket_init(State) ->
    ok = data_router:subscribe(),
    lager:info("WebSocket client connected (~p)", [self()]),
    {ok, State#{subscribed_symbols => all}}.

-spec websocket_handle(Frame :: cowboy_websocket:frame(), State :: map()) ->
    {ok, map()} | {reply, cowboy_websocket:frame(), map()}.
websocket_handle({text, Msg}, State) ->
    handle_command(jsx:decode(Msg, [return_maps]), State);
websocket_handle({ping, _}, State) ->
    {reply, {pong, <<>>}, State};
websocket_handle(_Frame, State) ->
    {ok, State}.

-spec websocket_info(Info :: term(), State :: map()) ->
    {ok, map()} | {reply, cowboy_websocket:frame(), map()}.
websocket_info({data_event, Event}, State) ->
    case should_forward(Event, State) of
        true ->
            Json = jsx:encode(normalise_event(Event)),
            {reply, {text, Json}, State};
        false ->
            {ok, State}
    end;
websocket_info(_Info, State) ->
    {ok, State}.

-spec terminate(Reason :: term(), Req :: any(), State :: map()) -> ok.
terminate(_Reason, _Req, _State) ->
    data_router:unsubscribe(),
    lager:info("WebSocket client disconnected (~p)", [self()]),
    ok.

%%=============================================================================
%% Internal helpers
%%=============================================================================

-spec handle_command(Cmd :: map(), State :: map()) ->
    {ok, map()} | {reply, cowboy_websocket:frame(), map()}.
handle_command(#{<<"cmd">> := <<"ping">>}, State) ->
    {reply, {text, jsx:encode(#{type => <<"pong">>,
                                timestamp => erlang:system_time(millisecond)})},
     State};

handle_command(#{<<"cmd">> := <<"subscribe">>, <<"symbols">> := Syms}, State) ->
    {ok, State#{subscribed_symbols => Syms}};

handle_command(#{<<"cmd">> := <<"unsubscribe">>}, State) ->
    {ok, State#{subscribed_symbols => []}};

handle_command(#{<<"cmd">> := <<"get_cache">>, <<"key">> := Key}, State) ->
    CacheKey = parse_cache_key(Key),
    Reply    = case ets_cache:get(CacheKey) of
        {ok, Value} -> #{type => <<"cache_hit">>,  key => Key, payload => Value};
        not_found   -> #{type => <<"cache_miss">>,  key => Key}
    end,
    {reply, {text, jsx:encode(Reply)}, State};

handle_command(_, State) ->
    {reply, {text, jsx:encode(#{type => <<"error">>, message => <<"unknown command">>})},
     State}.

-spec should_forward(Event :: map(), State :: map()) -> boolean().
should_forward(_, #{subscribed_symbols := all}) -> true;
should_forward(#{symbol := Sym}, #{subscribed_symbols := Syms}) ->
    lists:member(Sym, Syms);
should_forward(_, _) -> true.

-spec normalise_event(Event :: map()) -> map().
normalise_event(Event) ->
    maps:map(fun(_K, V) when is_atom(V) -> atom_to_binary(V, utf8);
                (_K, V)                  -> V
             end, Event).

-spec parse_cache_key(Key :: binary()) -> term().
parse_cache_key(<<"tick:", Symbol/binary>>)        -> {tick, Symbol};
parse_cache_key(<<"fundamental:", Symbol/binary>>) -> {fundamental, Symbol};
parse_cache_key(<<"weather:", Symbol/binary>>)     -> {weather, Symbol};
parse_cache_key(<<"macro:", Symbol/binary>>)        -> {macro, Symbol};
parse_cache_key(Key)                                -> Key.
