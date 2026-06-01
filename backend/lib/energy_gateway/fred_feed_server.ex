defmodule EnergyGateway.FredFeedServer do
  use GenServer

  require Logger

  @name __MODULE__
  @base_url "https://api.stlouisfed.org/fred/series/observations"
  @endpoint :fred

  @series_ids [
    "DTWEXBGS",
    "CPIAUCSL",
    "REAINTRATREARAT10Y",
    "INDPRO",
    "DCOILWTICO"
  ]

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def force_poll do
    GenServer.cast(@name, :poll)
  end

  @impl true
  def init(_) do
    api_key = System.get_env("FRED_API_KEY", "")
    Process.send_after(self(), :poll, 4_000)
    Logger.info("FRED feed started (key present: #{api_key != ""})")
    {:ok, %{interval: 14_400_000, api_key: api_key}}
  end

  @impl true
  def handle_cast(:poll, state) do
    do_poll(state)
    {:noreply, state}
  end

  @impl true
  def handle_info(:poll, %{interval: interval} = state) do
    do_poll(state)
    Process.send_after(self(), :poll, interval)
    {:noreply, state}
  end

  def handle_info(:force_poll, state) do
    do_poll(state)
    {:noreply, state}
  end

  def handle_info(_msg, state), do: {:noreply, state}

  defp do_poll(%{api_key: ""}) do
    Logger.info("FRED API key absent; skipping")
    :ok
  end

  defp do_poll(%{api_key: api_key}) do
    Enum.each(@series_ids, fn series ->
      case EnergyGateway.RateLimiter.check_and_consume(@endpoint) do
        :ok -> fetch_series(series, api_key)
        {:error, :rate_limited} -> Logger.warning("FRED rate limited for #{series}")
      end
    end)
  end

  defp fetch_series(series_id, api_key) do
    url =
      "#{@base_url}?series_id=#{series_id}&api_key=#{api_key}&file_type=json&sort_order=desc&limit=1"

    case http_client().get(url, [], "", [:with_body]) do
      {:ok, 200, _headers, body} -> parse_and_publish(series_id, body)
      {:ok, status, _headers, _body} -> Logger.warning("FRED #{series_id} returned HTTP #{status}")
      {:error, reason} -> Logger.error("FRED #{series_id} error: #{inspect(reason)}")
    end
  end

  defp parse_and_publish(series_id, body) do
    with {:ok, decoded} <- Jason.decode(body),
         %{"observations" => [obs | _]} <- decoded do
      value = Map.get(obs, "value", "")
      num_value = parse_value(value)
      date = Map.get(obs, "date", "")
      series_bin = series_id
      payload = %{"series" => series_bin, "value" => num_value, "date" => date}
      EnergyGateway.EtsCache.put({:macro, series_bin}, payload)
      EnergyGateway.DataRouter.publish(%{
        "type" => "macro",
        "source" => "fred",
        "symbol" => series_bin,
        "timestamp" => System.system_time(:millisecond),
        "payload" => payload
      })
    else
      _ -> Logger.error("FRED parse error for #{series_id}")
    end
  end

  defp parse_value("."), do: nil
  defp parse_value(value) when is_binary(value) do
    case Float.parse(value) do
      {float, _} -> float
      :error -> nil
    end
  end

  defp http_client do
    Application.get_env(:energy_gateway, :http_client, EnergyGateway.HttpClient)
  end
end
