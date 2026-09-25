# Sourced by each adapter's run.sh (after setting $here to the adapter dir).
#
#   adapter_exec <pixi-env> <command...>
#
# runs the command in the adapter's environment:
#   BRASSCRIBE_ADAPTER_RUNNER=uv    (default) the uv project next to run.sh
#   BRASSCRIBE_ADAPTER_RUNNER=pixi  the pixi environment <pixi-env> of the repo's pixi.toml;
#                                   BRASSCRIBE_CUDA=1 selects <pixi-env>-cuda for torch adapters
adapter_exec() {
  env_name=$1
  shift
  if [ "${BRASSCRIBE_ADAPTER_RUNNER:-uv}" = pixi ]; then
    pixi run --manifest-path "$here/../../../pixi.toml" --frozen -e "$env_name" "$@"
  else
    uv run --project "$here" "$@"
  fi
}

# Environment name for a torch adapter: <name>, or <name>-cuda when BRASSCRIBE_CUDA is set.
torch_env() {
  if [ -n "${BRASSCRIBE_CUDA:-}" ]; then echo "$1-cuda"; else echo "$1"; fi
}
