defmodule EnergyGateway.EtsCacheTest do
  use ExUnit.Case, async: true

  setup do
    if Process.whereis(EnergyGateway.EtsCache), do: :ok, else: EnergyGateway.EtsCache.start_link(nil)
    :ok
  end

  test "put and get roundtrip" do
    assert :ok == EnergyGateway.EtsCache.put(:foo, %{value: 1})
    assert {:ok, %{value: 1}} = EnergyGateway.EtsCache.get(:foo)
  end

  test "get_fresh returns stale when too old" do
    assert :ok == EnergyGateway.EtsCache.put(:old, %{value: 2})
    assert {:ok, _} = EnergyGateway.EtsCache.get(:old)
    Process.sleep(1100)
    assert :stale = EnergyGateway.EtsCache.get_fresh(:old, 0)
  end
end
