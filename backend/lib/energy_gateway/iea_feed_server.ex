defmodule EnergyGateway.IeaFeedServer do
  use GenServer

  require Logger

  @name __MODULE__
  @base_url "https://api.iea.org/stats/"
  @endpoint :iea

  @queries [
    {"OILFUTURES", "OECD_STOCKS", "TOTIND", "KBBL"},
    {"OILFUTURES", "WORLD_DEMAND", "TOTAL", "MBDOE"},
    {"OILFUTURES", "WORLD_SUPPLY", "TOTAL", "MBDOE"}
  ]

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def force_poll do
    GenServer.cast(@name, :poll)
  end

  @impl true
  def init(_) do
    api_key = System.get_env("IEA_API_KEY", "")

    state =
      if api_key == "" do
        Logger.warning("IEA feed: IEA_API_KEY not set — feed inactive")
        %{active: false, api_key: ""}
      else
        Process.send_after(self(), :poll, 5_000)
        Logger.info("IEA feed server started")
        %{active: true, api_key: api_key, interval: 21_600_000}
      end

    {:ok, state}
  end

  @impl true
  def handle_cast(:poll, %{active: true} = state) do
    do_poll(state)
    {:noreply, state}
  end

  def handle_cast(:poll, state), do: {:noreply, state}

  @impl true
  def handle_info(:poll, %{active: true, interval: interval} = state) do
    do_poll(state)
    Process.send_after(self(), :poll, interval)
    {:noreply, state}
  end

  def handle_info(:poll, state), do: {:noreply, state}
  def handle_info(:force_poll, state), do: {:noreply, state}
  def handle_info(_msg, state), do: {:noreply, state}

  defp do_poll(%{api_key: api_key}) do
    Enum.each(@queries, fn {dataset, product, flow, unit} ->
      case EnergyGateway.RateLimiter.check_and_consume(@endpoint) do
        :ok -> fetch_and_publish(dataset, product, flow, unit, api_key)
        {:error, :rate_limited} -> Logger.warning("IEA rate limit hit for #{dataset}/#{product}")
      end
    end)
  end

  defp fetch_and_publish(dataset, product, flow, unit, api_key) do
    url =
      "#{@base_url}#{dataset}?products=#{product}&flows=#{flow}&unit=#{unit}&last=1"

    headers = [
      {"Authorization", "Bearer #{api_key}"},
      {"Accept", "application/json"}
    ]

    case http_client().get(url, headers, "", [:with_body]) do
      {:ok, 200, _headers, body} -> parse_and_publish(dataset, product, flow, body)
      {:ok, 401, _headers, _body} -> Logger.error("IEA API key rejected (401)")
      {:ok, status, _headers, _body} -> Logger.warning("IEA #{dataset} returned HTTP #{status}")
      {:error, reason} -> Logger.error("IEA fetch error: #{inspect(reason)}")
    end
  end

  defp parse_and_publish(dataset, product, flow, body) do
    with {:ok, decoded} <- Jason.decode(body),
         %{"data" => [latest | _]} <- decoded do
      value = Map.get(latest, "value", nil)
      period = Map.get(latest, "time", nil)
      key = "#{dataset}.#{product}.#{flow}"
      payload = %{
        "dataset" => dataset,
        "product" => product,
        "flow" => flow,
        "value" => value,
        "period" => period
      }

      EnergyGateway.EtsCache.put({:fundamental, key}, payload)
      EnergyGateway.DataRouter.publish(%{
        "type" => "fundamental",
        "source" => "iea",
        "symbol" => key,
        "timestamp" => System.system_time(:millisecond),
        "payload" => payload
      })
    else
      _ -> Logger.error("IEA parse error #{dataset}: #{inspect(body)}")
    end
  end

  defp http_client do
    Application.get_env(:energy_gateway, :http_client, EnergyGateway.HttpClient)
  end
end
