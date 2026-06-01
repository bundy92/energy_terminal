if Application.started_applications() |> Enum.any?(fn {app, _, _} -> app == :energy_gateway end) do
  Application.stop(:energy_gateway)
end

ExUnit.start()
