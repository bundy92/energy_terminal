defmodule EnergyGateway.HttpClient do
  @moduledoc false

  def get(url, headers, body, opts) do
    :hackney.get(url, headers, body, opts)
  end
end
