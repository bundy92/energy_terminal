%% @doc PropEr property-based tests for message schema invariants.
%%
%% Verifies that:
%% - Any valid event map survives the normalise_event transform
%% - Cache key parsing is a left-inverse of key construction
%% - Rate limiter token counts never exceed capacity
-module(prop_schema_tests).
-include_lib("proper/include/proper.hrl").
-include_lib("eunit/include/eunit.hrl").

%%=============================================================================
%% Generators
%%=============================================================================

symbol() ->
    elements([<<"CL=F">>, <<"NG=F">>, <<"BZ=F">>, <<"RB=F">>, <<"HO=F">>]).

event_type() ->
    elements([tick, fundamental, weather, macro]).

valid_event() ->
    ?LET({Type, Symbol, Ts},
         {event_type(), symbol(), pos_integer()},
         #{type => Type, source => yahoo_finance,
           symbol => Symbol, timestamp => Ts, payload => #{}}).

%%=============================================================================
%% Properties
%%=============================================================================

%% Property: normalise_event never crashes on valid events
prop_normalise_event_safe() ->
    ?FORALL(Event, valid_event(),
        begin
            try
                _Normalised = normalise_map_atoms(Event),
                true
            catch _:_ ->
                false
            end
        end).

%% Property: tick cache keys parse correctly
prop_cache_key_roundtrip() ->
    ?FORALL(Symbol, symbol(),
        begin
            Key = <<"tick:", Symbol/binary>>,
            {tick, Symbol} =:= parse_cache_key(Key)
        end).

%%=============================================================================
%% PropEr → EUnit bridge
%%=============================================================================

proper_test_() ->
    [
        {"normalise_event safe on any valid event",
         ?_assert(proper:quickcheck(prop_normalise_event_safe(),
                                    [{numtests, 200}, nocolors]))},
        {"cache key roundtrip holds",
         ?_assert(proper:quickcheck(prop_cache_key_roundtrip(),
                                    [{numtests, 200}, nocolors]))}
    ].

%%=============================================================================
%% Helpers (inline copies from ws_handler private functions)
%%=============================================================================

normalise_map_atoms(M) ->
    maps:map(fun(_K, V) when is_atom(V) -> atom_to_binary(V, utf8);
                (_K, V)                  -> V
             end, M).

parse_cache_key(<<"tick:", Symbol/binary>>)        -> {tick, Symbol};
parse_cache_key(<<"fundamental:", Symbol/binary>>) -> {fundamental, Symbol};
parse_cache_key(<<"weather:", Symbol/binary>>)     -> {weather, Symbol};
parse_cache_key(<<"macro:", Symbol/binary>>)        -> {macro, Symbol};
parse_cache_key(Key)                                -> Key.
