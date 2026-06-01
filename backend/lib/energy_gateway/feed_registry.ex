defmodule EnergyGateway.FeedRegistry do
  use GenServer

  @name __MODULE__

  @feeds [
    market_feed_server: EnergyGateway.MarketFeedServer,
    eia_feed_server: EnergyGateway.EiaFeedServer,
    weather_feed_server: EnergyGateway.WeatherFeedServer,
    fred_feed_server: EnergyGateway.FredFeedServer
  ]

  def start_link(_) do
    GenServer.start_link(__MODULE__, %{}, name: @name)
  end

  def lookup(feed) when is_atom(feed) do
    GenServer.call(@name, {:lookup, feed})
  end

  def all do
    GenServer.call(@name, :all)
  end

  def force_poll(feed) when is_atom(feed) do
    GenServer.call(@name, {:force_poll, feed})
  end

  @impl true
  def init(_) do
    Process.send_after(self(), :register_feeds, 2_000)
    {:ok, %{}}
  end

  @impl true
  def handle_call({:lookup, feed}, _from, state) do
    {:reply, Map.fetch(state, feed), state}
  end

  def handle_call(:all, _from, state) do
    status =
      state
      |> Enum.map(fn {name, pid} -> {name, if(Process.alive?(pid), do: :alive, else: :dead)} end)

    {:reply, status, state}
  end

  def handle_call({:force_poll, feed}, _from, state) do
    case Map.fetch(state, feed) do
      {:ok, pid} when is_pid(pid) ->
        if Process.alive?(pid) do
          send(pid, :force_poll)
          {:reply, :ok, state}
        else
          {:reply, {:error, :not_found}, state}
        end

      _ ->
        {:reply, {:error, :not_found}, state}
    end
  end

  @impl true
  def handle_info(:register_feeds, _state) do
    registry =
      Enum.reduce(@feeds, %{}, fn {name, module}, acc ->
        case Process.whereis(module) do
          nil -> acc
          pid -> Map.put(acc, name, pid)
        end
      end)

    {:noreply, registry}
  end

  def handle_info(_message, state), do: {:noreply, state}
end
