const CONTEXT_NAME = 'askai:end-user-login'

export class RuntimeEndUserContext {
  #loginName = ''
  #dispose

  install(ctx, loginName) {
    this.#loginName = typeof loginName === 'string' ? loginName.trim() : ''
    if (!this.#loginName) return
    this.#dispose = ctx.systemPrompt.context({
      name: CONTEXT_NAME,
      order: 25,
      text: () => `Current user login: ${this.#loginName}`,
    })
  }

  dispose() {
    this.#loginName = ''
    this.#dispose?.()
    this.#dispose = undefined
  }
}
