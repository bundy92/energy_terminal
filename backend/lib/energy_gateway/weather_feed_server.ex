defmodule EnergyGateway.WeatherFeedServer do
  use GenServer

  require Logger

  @name __MODULE__
  @base_url "https://api.open-meteo.com/v1/forecast"
  @base_temp_c 18.3
  @endpoint :open_meteo

  @locations [
    %{name: "New York", lat: 40.71, lon: -74.01},
    %{name: "Chicago", lat: 41.88, lon: -87.63},
    %{name: "Houston", lat: 29.76, lon: -95.37},
    %{name: "London", lat: 51.51, lon: -0.12},
    %{name: "Rotterdam", lat: 51.92, lon: 4.48},
    %{name: "Tokyo", lat: 35.69, lon: 139.69}
  ]

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def force_poll do
    GenServer.cast(@name, :poll)
  end

  @impl true
  def init(_) do
    Process.send_after(self(), :poll, 3_000)
    {:ok, %{interval: 10_800_000}}
  end

  @impl true
  def handle_cast(:poll, state) do
    do_poll()
    {:noreply, state}
  end

  @impl true
  def handle_info(:poll, %{interval: interval} = state) do
    do_poll()
    Process.send_after(self(), :poll, interval)
    {:noreply, state}
  end

  def handle_info(:force_poll, state) do
    do_poll()
    {:noreply, state}
  end

  def handle_info(_msg, state), do: {:noreply, state}

  defp do_poll do
    Enum.each(@locations, &fetch_location/1)
  end

  defp fetch_location(%{name: name, lat: lat, lon: lon}) do
    case EnergyGateway.RateLimiter.check_and_consume(@endpoint) do
      {:error, :rate_limited} -> Logger.warning("Open-Meteo rate limited for #{name}")
      :ok ->
        url =
          "#{@base_url}?latitude=#{lat}&longitude=#{lon}&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min&forecast_days=7&timezone=auto"

        fetch_and_publish(url, name)
    end
  end

  defp fetch_and_publish(url, name) do
    case http_client().get(url, [], "", [:with_body]) do
      {:ok, 200, _headers, body} -> parse_weather(body, name)
      {:ok, status, _headers, _body} -> Logger.warning("Open-Meteo #{name} returned #{status}")
      {:error, reason} -> Logger.error("Open-Meteo error for #{name}: #{inspect(reason)}")
    end
  end

  defp parse_weather(body, name) do
    with {:ok, decoded} <- Jason.decode(body),
         temp_c when is_number(temp_c) <- get_in(decoded, ["current", "temperature_2m"]),
         max_list when is_list(max_list) <- get_in(decoded, ["daily", "temperature_2m_max"]),
         min_list when is_list(min_list) <- get_in(decoded, ["daily", "temperature_2m_min"]) do
      forecast_7d = Enum.zip(max_list, min_list) |> Enum.map(fn {mx, mn} -> (mx + mn) / 2 end)
      hdd = max(0, @base_temp_c - temp_c)
      cdd = max(0, temp_c - @base_temp_c)
      payload = %{
        "location" => name,
        "temp_c" => temp_c,
        "hdd" => hdd,
        "cdd" => cdd,
        "forecast_7d" => forecast_7d
      }

      EnergyGateway.EtsCache.put({:weather, name}, payload)
      EnergyGateway.DataRouter.publish(%{
        "type" => "weather",
        "source" => "open_meteo",
        "symbol" => name,
        "timestamp" => System.system_time(:millisecond),
        "payload" => payload
      })
    else
      _ -> Logger.error("Weather parse error for #{name}")
    end
  end

  defp http_client do
    Application.get_env(:energy_gateway, :http_client, EnergyGateway.HttpClient)
  end
end
