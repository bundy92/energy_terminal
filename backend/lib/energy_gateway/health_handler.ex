defmodule EnergyGateway.HealthHandler do
  def init(req, state) do
    start_time = Application.get_env(:energy_gateway, :start_time, System.monotonic_time(:second))
    uptime_s = System.monotonic_time(:second) - start_time

    body = Jason.encode!(%{
      status: "ok",
      subscribers: EnergyGateway.DataRouter.subscriber_count(),
      cache_keys: length(EnergyGateway.EtsCache.keys()),
      uptime_s: uptime_s
    })

    req2 = :cowboy_req.reply(200, %{"content-type" => "application/json"}, body, req)
    {:ok, req2, state}
  end
end
