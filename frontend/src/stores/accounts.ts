import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { accountsApi } from '@/api'
import type { AdminAccount, AccountConfigItem } from '@/types/api'

type AccountOpResult = {
  ok: boolean
  errors: string[]
}

type RunOpOptions = {
  accountIds?: string[]
  lockKeys?: string[]
  chunkSize?: number
  request: (chunk: string[]) => Promise<{ errors?: string[] } | void>
  refreshAfter?: boolean
}

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<AdminAccount[]>([])
  const isLoading = ref(false)
  const operatingAccounts = ref<Set<string>>(new Set())
  const batchProgress = ref<{ current: number; total: number } | null>(null)

  const isOperating = computed(() => operatingAccounts.value.size > 0)

  const LOCK_TIMEOUT_MS = 60000

  async function loadAccounts() {
    isLoading.value = true
    try {
      const response = await accountsApi.list()
      if (Array.isArray(response)) {
        accounts.value = response
      } else {
        accounts.value = response.accounts || []
      }
    } finally {
      isLoading.value = false
    }
  }

  const addLocks = (locks: string[]) => {
    locks.forEach(lock => operatingAccounts.value.add(lock))
  }

  const releaseLocks = (locks: string[]) => {
    locks.forEach(lock => operatingAccounts.value.delete(lock))
  }

  const buildChunks = (ids: string[], chunkSize: number) => {
    const chunks: string[][] = []
    for (let i = 0; i < ids.length; i += chunkSize) {
      chunks.push(ids.slice(i, i + chunkSize))
    }
    return chunks
  }

  const startTimeoutGuard = (locks: string[]) => {
    if (!locks.length) return null
    return window.setTimeout(() => {
      releaseLocks(locks)
      batchProgress.value = null
    }, LOCK_TIMEOUT_MS)
  }

  async function runAccountOp(options: RunOpOptions): Promise<AccountOpResult> {
    const accountIds = options.accountIds ?? []
    const lockKeys = options.lockKeys ?? accountIds
    const chunkSize = options.chunkSize ?? 10
    const refreshAfter = options.refreshAfter ?? true

    if (!lockKeys.length && !accountIds.length) {
      return { ok: true, errors: [] }
    }

    const conflict = lockKeys.filter(id => operatingAccounts.value.has(id))
    if (conflict.length > 0) {
      throw new Error(`${conflict.length} 个账号正在操作中`)
    }

    addLocks(lockKeys)
    const timeoutGuard = startTimeoutGuard(lockKeys)

    if (accountIds.length > 1) {
      batchProgress.value = { current: 0, total: accountIds.length }
    }

    const errors: string[] = []
    try {
      const chunks = accountIds.length ? buildChunks(accountIds, chunkSize) : [[]]
      for (const chunk of chunks) {
        const response = await options.request(chunk)
        if (response && Array.isArray(response.errors) && response.errors.length) {
          errors.push(...response.errors)
        }
        if (batchProgress.value) {
          batchProgress.value.current += chunk.length
        }
      }
      if (refreshAfter) {
        await loadAccounts()
      }
      return { ok: errors.length === 0, errors }
    } finally {
      if (timeoutGuard !== null) {
        window.clearTimeout(timeoutGuard)
      }
      releaseLocks(lockKeys)
      batchProgress.value = null
    }
  }

  async function deleteAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.delete(chunk[0])
      },
    })
  }

  async function disableAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.disable(chunk[0])
      },
    })
  }

  async function enableAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.enable(chunk[0])
      },
    })
  }

  async function bulkEnable(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      request: async (chunk) => accountsApi.bulkEnable(chunk),
    })
  }

  async function bulkDisable(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      request: async (chunk) => accountsApi.bulkDisable(chunk),
    })
  }

  async function bulkDelete(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      request: async (chunk) => accountsApi.bulkDelete(chunk),
    })
  }

  async function syncAccounts(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      refreshAfter: false,
      request: async (chunk) => accountsApi.syncAccounts(chunk),
    })
  }

  async function updateConfig(newAccounts: AccountConfigItem[]) {
    return runAccountOp({
      lockKeys: ['__config_update__'],
      request: async () => {
        await accountsApi.updateConfig(newAccounts)
      },
    })
  }

  return {
    accounts,
    isLoading,
    isOperating,
    batchProgress,
    loadAccounts,
    deleteAccount,
    disableAccount,
    enableAccount,
    bulkEnable,
    bulkDisable,
    bulkDelete,
    updateConfig,
    syncAccounts,
  }
})
