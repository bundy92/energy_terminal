defmodule EnergyGateway.WsHandler do
  @behaviour :cowboy_websocket

  require Logger

  @impl true
  def init(req, _state) do
    {:cowboy_websocket, req, %{}}
  end

  @impl true
  def websocket_init(state) do
    EnergyGateway.DataRouter.subscribe()
    Logger.info("WebSocket client connected: #{inspect(self())}")
    {:ok, Map.put(state, :subscribed_symbols, :all)}
  end

  @impl true
  def websocket_handle({:text, msg}, state) do
    case Jason.decode(msg) do
      {:ok, command} -> handle_command(command, state)
      {:error, _} ->
        {:reply, {:text, Jason.encode!(%{"type" => "error", "message" => "invalid json"})}, state}
    end
  end

  def websocket_handle(_frame, state), do: {:ok, state}

  @impl true
  def websocket_info({:data_event, event}, state) do
    if should_forward?(event, state) do
      {:reply, {:text, Jason.encode!(normalize_event(event))}, state}
    else
      {:ok, state}
    end
  end

  def websocket_info(_info, state), do: {:ok, state}

  @impl true
  def terminate(_reason, _req, _state) do
    EnergyGateway.DataRouter.unsubscribe()
    Logger.info("WebSocket client disconnected: #{inspect(self())}")
    :ok
  end

  defp handle_command(%{"cmd" => "ping"}, state) do
    reply = %{"type" => "pong", "timestamp" => System.system_time(:millisecond)}
    {:reply, {:text, Jason.encode!(reply)}, state}
  end

  defp handle_command(%{"cmd" => "subscribe", "symbols" => symbols}, state) when is_list(symbols) do
    symbols = if symbols == ["all"], do: :all, else: symbols
    {:ok, Map.put(state, :subscribed_symbols, symbols)}
  end

  defp handle_command(%{"cmd" => "unsubscribe"}, state) do
    {:ok, Map.put(state, :subscribed_symbols, [])}
  end

  defp handle_command(%{"cmd" => "get_cache", "key" => key}, state) when is_binary(key) do
    reply = case EnergyGateway.EtsCache.get(parse_cache_key(key)) do
      {:ok, value} -> %{"type" => "cache_hit", "key" => key, "payload" => value}
      :not_found -> %{"type" => "cache_miss", "key" => key}
    end

    {:reply, {:text, Jason.encode!(reply)}, state}
  end

  defp handle_command(_unknown, state) do
    reply = %{"type" => "error", "message" => "unknown command"}
    {:reply, {:text, Jason.encode!(reply)}, state}
  end

  defp should_forward?(_event, %{subscribed_symbols: :all}), do: true

  defp should_forward?(%{"symbol" => symbol}, %{subscribed_symbols: symbols}) when is_list(symbols) do
    symbol in symbols
  end

  defp should_forward?(_, _), do: true

  defp normalize_event(event) when is_map(event) do
    event
    |> Enum.map(fn {key, value} -> {to_string(key), normalize_value(value)} end)
    |> Map.new()
  end

  defp normalize_value(value) when is_map(value), do: normalize_event(value)
  defp normalize_value(value) when is_atom(value), do: Atom.to_string(value)
  defp normalize_value(value), do: value

  defp parse_cache_key("tick:" <> symbol), do: {:tick, symbol}
  defp parse_cache_key("fundamental:" <> symbol), do: {:fundamental, symbol}
  defp parse_cache_key("weather:" <> symbol), do: {:weather, symbol}
  defp parse_cache_key("macro:" <> symbol), do: {:macro, symbol}
  defp parse_cache_key(key), do: key
end
