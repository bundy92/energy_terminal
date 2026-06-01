defmodule EnergyGateway.DataRouter do
  use GenServer

  @name __MODULE__

  def start_link(_) do
    GenServer.start_link(__MODULE__, MapSet.new(), name: @name)
  end

  def subscribe do
    GenServer.call(@name, {:subscribe, self()})
  end

  def unsubscribe do
    GenServer.call(@name, {:unsubscribe, self()})
  end

  def publish(event) when is_map(event) do
    GenServer.cast(@name, {:publish, event})
  end

  def subscriber_count do
    GenServer.call(@name, :subscriber_count)
  end

  @impl true
  def init(_) do
    {:ok, MapSet.new()}
  end

  @impl true
  def handle_call({:subscribe, pid}, _from, subscribers) do
    Process.monitor(pid)
    {:reply, :ok, MapSet.put(subscribers, pid)}
  end

  def handle_call({:unsubscribe, pid}, _from, subscribers) do
    {:reply, :ok, MapSet.delete(subscribers, pid)}
  end

  def handle_call(:subscriber_count, _from, subscribers) do
    {:reply, MapSet.size(subscribers), subscribers}
  end

  @impl true
  def handle_cast({:publish, event}, subscribers) do
    Enum.each(subscribers, fn pid -> send(pid, {:data_event, event}) end)
    {:noreply, subscribers}
  end

  @impl true
  def handle_info({:DOWN, _ref, :process, pid, _reason}, subscribers) do
    {:noreply, MapSet.delete(subscribers, pid)}
  end

  def handle_info(_message, state), do: {:noreply, state}
end
