defmodule EnergyGateway.RateLimiter do
  use GenServer

  require Logger

  @name __MODULE__
  @max_wait_ms 5_000
  @refill_tick 1_000

  defmodule Bucket do
    defstruct [:tokens, :capacity, :rate_ps]
  end

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  def check_and_consume(endpoint) do
    GenServer.call(@name, {:consume, endpoint}, @max_wait_ms)
  end

  def status do
    GenServer.call(@name, :status)
  end

  @impl true
  def init(_) do
    rates = Application.get_env(:energy_gateway, :rate_limits, [])

    buckets =
      rates
      |> Enum.into(%{}, fn {endpoint, rpm} ->
        rate_ps = rpm / 60.0
        {endpoint, %Bucket{tokens: rate_ps, capacity: rate_ps, rate_ps: rate_ps}}
      end)

    Logger.info("Rate limiter initialized for #{map_size(buckets)} endpoints")
    Process.send_after(self(), :refill, @refill_tick)
    {:ok, buckets}
  end

  @impl true
  def handle_call({:consume, endpoint}, _from, buckets) do
    case Map.fetch(buckets, endpoint) do
      :error ->
        Logger.warning("Unknown endpoint #{inspect(endpoint)}, bypassing rate limit")
        {:reply, :ok, buckets}

      {:ok, %Bucket{tokens: tokens} = bucket} when tokens >= 1.0 ->
        updated = %{bucket | tokens: tokens - 1.0}
        {:reply, :ok, Map.put(buckets, endpoint, updated)}

      {:ok, _bucket} ->
        {:reply, {:error, :rate_limited}, buckets}
    end
  end

  def handle_call(:status, _from, buckets) do
    summary =
      buckets
      |> Enum.into(%{}, fn {endpoint, %Bucket{tokens: tokens, capacity: capacity, rate_ps: rate_ps}} ->
        {endpoint, %{tokens: tokens, capacity: capacity, rate_ps: rate_ps}}
      end)

    {:reply, summary, buckets}
  end

  def handle_call(_request, _from, state), do: {:reply, :ok, state}

  @impl true
  def handle_cast(_message, state), do: {:noreply, state}

  @impl true
  def handle_info(:refill, buckets) do
    refilled =
      Enum.into(buckets, %{}, fn {endpoint, %Bucket{tokens: tokens, capacity: capacity, rate_ps: rate_ps} = bucket} ->
        new_tokens = min(capacity, tokens + rate_ps)
        {endpoint, %{bucket | tokens: new_tokens}}
      end)

    Process.send_after(self(), :refill, @refill_tick)
    {:noreply, refilled}
  end

  def handle_info(_message, state), do: {:noreply, state}
end
