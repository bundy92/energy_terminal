defmodule EnergyGateway.EiaFeedServer do
  use GenServer

  require Logger

  @name __MODULE__
  @base_url "https://api.eia.gov/v2/seriesid/"
  @endpoint :eia
  @series [
    "PET.WCRSTUS1.W",
    "PET.WCRFPUS2.W",
    "PET.WCRRIUS2.W",
    "PET.WPULEUS2.W",
    "NG.NW2EUS_EPG0_SWO_BCF.W"
  ]

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def force_poll do
    GenServer.cast(@name, :poll)
  end

  @impl true
  def init(_) do
    api_key = System.get_env("EIA_API_KEY", "")
    interval = Application.get_env(:energy_gateway, :poll_interval_ms, 3_600_000)
    Process.send_after(self(), :poll, 2_000)
    Logger.info("EIA feed server started (key present: #{api_key != ""})")
    {:ok, %{interval: interval, api_key: api_key}}
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
    Logger.info("EIA API key not set; skipping poll")
    :ok
  end

  defp do_poll(%{api_key: api_key}) do
    case EnergyGateway.RateLimiter.check_and_consume(@endpoint) do
      :ok -> Enum.each(@series, &fetch_series(&1, api_key))
      {:error, :rate_limited} -> Logger.warning("EIA rate limit hit")
    end
  end

  defp fetch_series(series, api_key) do
    url =
      "#{@base_url}#{series}?api_key=#{api_key}&data[]=value&sort[0][column]=period&sort[0][direction]=desc&length=1"

    case http_client().get(url, [], "", [:with_body]) do
      {:ok, 200, _headers, body} -> parse_and_publish(series, body)
      {:ok, status, _headers, _body} -> Logger.warning("EIA #{series} returned HTTP #{status}")
      {:error, reason} -> Logger.error("EIA #{series} fetch error: #{inspect(reason)}")
    end
  end

  defp parse_and_publish(series, body) do
    with {:ok, decoded} <- Jason.decode(body),
         %{"response" => %{"data" => [latest | _]}} <- decoded do
      value = Map.get(latest, "value", nil)
      period = Map.get(latest, "period", nil)
      series_bin = series
      payload = %{"series" => series_bin, "value" => value, "period" => period}
      EnergyGateway.EtsCache.put({:fundamental, series_bin}, payload)
      EnergyGateway.DataRouter.publish(%{
        "type" => "fundamental",
        "source" => "eia",
        "symbol" => series_bin,
        "timestamp" => System.system_time(:millisecond),
        "payload" => payload
      })
    else
      _ -> Logger.error("EIA parse error for #{series}")
    end
  end

  defp http_client do
    Application.get_env(:energy_gateway, :http_client, EnergyGateway.HttpClient)
  end
end
