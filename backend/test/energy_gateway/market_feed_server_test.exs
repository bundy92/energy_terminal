defmodule EnergyGateway.MarketFeedServerTest do
  use ExUnit.Case, async: false

  def quote_json do
    ~s({"quoteResponse":{"result":[{"symbol":"CL=F","regularMarketPrice":85.5,"regularMarketOpen":84.0,"regularMarketDayHigh":86.2,"regularMarketDayLow":83.8,"regularMarketVolume":150000,"regularMarketChange":1.5,"regularMarketChangePercent":1.79}],"error":null}})
  end

  setup do
    Application.put_env(:energy_gateway, :http_client, EnergyGateway.MarketFeedServerTest.MockHttpClient)
    Application.put_env(:energy_gateway, :poll_interval_ms, 999_999)
    Application.put_env(:energy_gateway, :instruments, ["CL=F"])

    start_if_needed(EnergyGateway.EtsCache)
    start_if_needed(EnergyGateway.DataRouter)
    start_if_needed(EnergyGateway.RateLimiter)
    start_if_needed(EnergyGateway.MarketFeedServer)

    on_exit(fn ->
      stop_if_started(EnergyGateway.MarketFeedServer)
      stop_if_started(EnergyGateway.DataRouter)
      stop_if_started(EnergyGateway.EtsCache)
      stop_if_started(EnergyGateway.RateLimiter)
    end)

    :ok
  end

  defp start_if_needed(module) do
    if Process.whereis(module), do: {:ok, Process.whereis(module)}, else: module.start_link(nil)
  end

  defp stop_if_started(module) do
    if pid = Process.whereis(module), do: Process.exit(pid, :normal)
  end

  test "force_poll writes tick to ETS cache" do
    EnergyGateway.MarketFeedServer.force_poll()
    Process.sleep(100)

    assert {:ok, %{"close" => 85.5}} = EnergyGateway.EtsCache.get({:tick, "CL=F"})
  end

  test "force_poll publishes router event" do
    EnergyGateway.DataRouter.subscribe()
    EnergyGateway.MarketFeedServer.force_poll()

    assert_receive {:data_event, %{"type" => "tick", "symbol" => "CL=F"}}, 1_000
    EnergyGateway.DataRouter.unsubscribe()
  end

  test "last_tick returns cached value" do
    EnergyGateway.MarketFeedServer.force_poll()
    Process.sleep(100)

    assert {:ok, %{"symbol" => "CL=F", "close" => 85.5}} = EnergyGateway.MarketFeedServer.last_tick("CL=F")
  end

  defmodule MockHttpClient do
    def get(_url, _headers, _body, _opts), do: {:ok, 200, [], EnergyGateway.MarketFeedServerTest.quote_json()}
  end
end
