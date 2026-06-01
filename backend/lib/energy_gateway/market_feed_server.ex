defmodule EnergyGateway.MarketFeedServer do
  use GenServer

  require Logger

  @name __MODULE__
  @base_url "https://query1.finance.yahoo.com/v7/finance/quote"
  @endpoint :yahoo_finance

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def force_poll do
    GenServer.cast(@name, :poll)
  end

  def last_tick(symbol) do
    EnergyGateway.EtsCache.get({:tick, symbol})
  end

  @impl true
  def init(_) do
    interval = Application.get_env(:energy_gateway, :poll_interval_ms, 30_000)
    instruments = Application.get_env(:energy_gateway, :instruments, [])

    Process.send_after(self(), :poll, 500)
    Logger.info("Market feed server started, #{length(instruments)} instruments, interval #{interval} ms")
    {:ok, %{interval: interval, instruments: instruments}}
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

  defp do_poll(%{instruments: []}) do
    Logger.warning("No instruments configured for Yahoo Finance feed")
    :ok
  end

  defp do_poll(%{instruments: instruments}) do
    case EnergyGateway.RateLimiter.check_and_consume(@endpoint) do
      :ok ->
        symbols = Enum.join(instruments, ",")
        url = "#{@base_url}?symbols=#{symbols}&fields=regularMarketPrice,regularMarketOpen,regularMarketDayHigh,regularMarketDayLow,regularMarketVolume,regularMarketChange,regularMarketChangePercent"
        fetch_and_publish(url)

      {:error, :rate_limited} ->
        Logger.warning("Yahoo Finance rate limit hit, skipping poll")
    end
  end

  defp fetch_and_publish(url) do
    headers = [{"User-Agent", "energy-terminal/0.1"}]

    case http_client().get(url, headers, "", [:with_body]) do
      {:ok, 200, _headers, body} ->
        process_response(body)

      {:ok, status, _headers, _body} ->
        Logger.warning("Yahoo Finance returned HTTP #{status}")

      {:error, reason} ->
        Logger.error("Yahoo Finance fetch error: #{inspect(reason)}")
    end
  end

  defp process_response(body) do
    case Jason.decode(body) do
      {:ok, %{"quoteResponse" => %{"result" => results}}} ->
        ts = System.system_time(:millisecond)
        Enum.each(results, &process_quote(&1, ts))

      {:ok, _} ->
        Logger.error("Yahoo Finance unexpected response shape")

      {:error, error} ->
        Logger.error("Yahoo Finance parse error: #{inspect(error)}")
    end
  end

  defp process_quote(%{"symbol" => symbol} = quote, ts) when is_binary(symbol) do
    tick = %{
      "symbol" => symbol,
      "open" => Map.get(quote, "regularMarketOpen", 0.0),
      "high" => Map.get(quote, "regularMarketDayHigh", 0.0),
      "low" => Map.get(quote, "regularMarketDayLow", 0.0),
      "close" => Map.get(quote, "regularMarketPrice", 0.0),
      "volume" => Map.get(quote, "regularMarketVolume", 0),
      "change" => Map.get(quote, "regularMarketChange", 0.0),
      "change_pct" => Map.get(quote, "regularMarketChangePercent", 0.0),
      "timestamp" => ts
    }

    EnergyGateway.EtsCache.put({:tick, symbol}, tick)
    EnergyGateway.DataRouter.publish(%{
      "type" => "tick",
      "source" => "yahoo_finance",
      "symbol" => symbol,
      "timestamp" => ts,
      "payload" => tick
    })
  end

  defp process_quote(_, _), do: :ok

  defp http_client do
    Application.get_env(:energy_gateway, :http_client, EnergyGateway.HttpClient)
  end
end
