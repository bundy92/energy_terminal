defmodule EnergyGateway.EtsCache do
  use GenServer

  require Logger

  @table :energy_cache
  @name __MODULE__

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def put(key, value) do
    ts = System.monotonic_time(:second)
    true = :ets.insert(@table, {key, value, ts})
    :ok
  end

  def get(key) do
    case :ets.lookup(@table, key) do
      [{^key, value, _ts}] -> {:ok, value}
      [] -> :not_found
    end
  end

  def get_fresh(key, max_age_secs) do
    now = System.monotonic_time(:second)

    case :ets.lookup(@table, key) do
      [{^key, value, ts}] when now - ts <= max_age_secs -> {:ok, value}
      [{^key, _value, _ts}] -> :stale
      [] -> :not_found
    end
  end

  def delete(key) do
    true = :ets.delete(@table, key)
    :ok
  end

  def keys do
    :ets.tab2list(@table)
    |> Enum.map(fn {key, _value, _ts} -> key end)
  end

  def flush do
    true = :ets.delete_all_objects(@table)
    :ok
  end

  @impl true
  def init(_) do
    :ets.new(@table, [:named_table, :public, :set, read_concurrency: true, write_concurrency: true])
    :ok = Logger.info("ETS cache initialized #{@table}")
    {:ok, nil}
  end
end
