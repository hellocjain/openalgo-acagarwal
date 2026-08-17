import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BarChart3,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  Copy,
  Download,
  FileText,
  Flame,
  Layers,
  Plus,
  Power,
  RefreshCw,
  Search,
  Send,
  Shield,
  Sliders,
  Sparkles,
  StopCircle,
  Trash2,
  TrendingDown,
  TrendingUp,
  UserPlus,
  Users,
  X,
  XCircle,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface AccountSummary {
  total_accounts: number
  active_accounts: number
  total_funds: number
  total_pnl: number
  master_switch_active?: boolean
}

interface ReadinessSummary {
  total_accounts: number
  ready_count: number
  need_login_count: number
  low_margin_count: number
  master_switch_active: boolean
}

interface Strategy {
  id: number
  strategy_tag: string
  strategy_name: string
  segment: string
  timeframe: string
  default_symbol: string
  description?: string
  is_active: boolean
  subscribers_count: number
  total_strategy_pnl?: number
  created_at?: string
}

interface ClientStrategyMapping {
  id: number
  account_id: number
  strategy_id: number
  strategy_tag?: string
  strategy_name?: string
  multiplier: number
  fixed_qty: number
  max_daily_loss: number
  daily_pnl: number
  is_active: boolean
  daily_loss_triggered: boolean
}

interface ChildAccount {
  id: number
  account_name: string
  client_code: string
  broker: string
  is_active: boolean
  is_primary?: boolean
  connection_status: string
  last_connected?: string
  error_message?: string
  sizing_mode: string
  multiplier: number
  fixed_qty: number
  max_lot_cap: number
  max_daily_loss: number
  daily_loss_triggered: boolean
  last_funds: number
  last_pnl: number
}

interface CopyOrderLog {
  id: number
  account_id: number
  account_name?: string
  client_code?: string
  strategy?: string
  symbol: string
  exchange: string
  action: string
  quantity: number
  price?: number
  pricetype: string
  product: string
  status: string
  message?: string
  execution_latency_ms: number
  created_at?: string
}

interface PlainFeedCard {
  timestamp: string
  type: 'success' | 'error' | 'warning'
  action: string
  symbol: string
  strategy: string
  total_clients: number
  successful: number
  failed: number
  latency_ms: number
  text: string
}

interface ClientProfileDetails {
  account: ChildAccount
  strategies: ClientStrategyMapping[]
  positions: Array<{
    symbol: string
    exchange: string
    quantity: number
    product: string
    avg_price: number
    pnl: number
  }>
  open_orders: Array<{
    order_id: string
    symbol: string
    action: string
    quantity: number
    price: number
    status: string
  }>
  recent_orders: CopyOrderLog[]
}

function formatCurrency(val: number): string {
  const isNeg = val < 0
  const abs = Math.abs(val)
  if (abs >= 10000000) return `${isNeg ? '-' : ''}₹${(abs / 10000000).toFixed(2)}Cr`
  if (abs >= 100000) return `${isNeg ? '-' : ''}₹${(abs / 100000).toFixed(2)}L`
  return `${isNeg ? '-' : ''}₹${abs.toFixed(2)}`
}

export default function CopyTrading() {
  const [summary, setSummary] = useState<AccountSummary>({
    total_accounts: 0,
    active_accounts: 0,
    total_funds: 0,
    total_pnl: 0,
    master_switch_active: true,
  })
  const [readiness, setReadiness] = useState<ReadinessSummary>({
    total_accounts: 0,
    ready_count: 0,
    need_login_count: 0,
    low_margin_count: 0,
    master_switch_active: true,
  })
  const [accounts, setAccounts] = useState<ChildAccount[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [logs, setLogs] = useState<CopyOrderLog[]>([])
  const [feed, setFeed] = useState<PlainFeedCard[]>([])
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [filterIssuesOnly, setFilterIssuesOnly] = useState<boolean>(false)

  // Modals & Drawers
  const [isAddAccountOpen, setIsAddAccountOpen] = useState<boolean>(false)
  const [isAddStrategyOpen, setIsAddStrategyOpen] = useState<boolean>(false)
  const [isFireDrillOpen, setIsFireDrillOpen] = useState<boolean>(false)
  const [fireDrillRunning, setFireDrillRunning] = useState<boolean>(false)
  const [fireDrillReport, setFireDrillReport] = useState<any>(null)

  // Client Detail Inspection Drawer
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [clientDetails, setClientDetails] = useState<ClientProfileDetails | null>(null)
  const [assignStrategyId, setAssignStrategyId] = useState<string>('')
  const [assignMultiplier, setAssignMultiplier] = useState<string>('1.0')
  const [assignMaxLoss, setAssignMaxLoss] = useState<string>('5000')

  // New Account Form State
  const [formData, setFormData] = useState({
    account_name: '',
    client_code: '',
    api_key: '',
    api_secret: '',
    api_key_market: '',
    api_secret_market: '',
    sizing_mode: 'MULTIPLIER',
    multiplier: 1.0,
    fixed_qty: 0,
    max_lot_cap: 50,
    max_daily_loss: 5000.0,
  })

  // New Strategy Form State
  const [strategyFormData, setStrategyFormData] = useState({
    strategy_tag: '',
    strategy_name: '',
    segment: 'MCXFO',
    timeframe: '15m',
    default_symbol: 'CRUDEOIL',
    description: '',
  })

  // Pro TradingView JSON Generator Modal State
  const [isJsonGeneratorOpen, setIsJsonGeneratorOpen] = useState<boolean>(false)
  const [copiedPayload, setCopiedPayload] = useState<boolean>(false)
  const [copiedPineScript, setCopiedPineScript] = useState<boolean>(false)
  const [testPingRunning, setTestPingRunning] = useState<boolean>(false)
  const [testPingResult, setTestPingResult] = useState<any>(null)
  const [jsonConfig, setJsonConfig] = useState({
    mode: 'strategy' as 'strategy' | 'indicator' | 'direct_client' | 'pinescript',
    strategy_tag: 'SILVER100',
    client_code: 'DM933',
    symbol: '{{ticker}}',
    exchange: 'MCXFO',
    action: '{{strategy.order.action}}',
    quantity: '{{strategy.order.contracts}}',
    position_size: true,
    price: '{{close}}',
    trigger_price: '',
    pricetype: 'MARKET',
    product: 'MIS',
  })

  const openJsonGenerator = (strat?: Strategy) => {
    if (strat) {
      setJsonConfig(prev => ({
        ...prev,
        strategy_tag: strat.strategy_tag,
        exchange: strat.segment || 'MCXFO',
        symbol: '{{ticker}}',
      }))
    }
    setTestPingResult(null)
    setIsJsonGeneratorOpen(true)
  }

  const generateWebhookPayloadString = () => {
    if (jsonConfig.mode === 'strategy') {
      let rawJson = `{\n  "strategy": "${jsonConfig.strategy_tag}",\n  "symbol": "${jsonConfig.symbol || '{{ticker}}'}",\n  "exchange": "${jsonConfig.exchange}",\n  "action": "${jsonConfig.action || '{{strategy.order.action}}'}",\n  "quantity": ${jsonConfig.quantity || '{{strategy.order.contracts}}'}`
      if (jsonConfig.position_size) {
        rawJson += `,\n  "position_size": {{strategy.position_size}}`
      }
      if (jsonConfig.price && jsonConfig.pricetype !== 'MARKET') {
        rawJson += `,\n  "price": ${jsonConfig.price || '{{close}}'}`
      }
      if (jsonConfig.trigger_price && (jsonConfig.pricetype === 'SL-M' || jsonConfig.pricetype === 'SL-L')) {
        rawJson += `,\n  "trigger_price": ${jsonConfig.trigger_price}`
      }
      rawJson += `,\n  "pricetype": "${jsonConfig.pricetype}",\n  "product": "${jsonConfig.product}"\n}`
      return rawJson
    } else if (jsonConfig.mode === 'direct_client') {
      const obj: any = {
        client_code: jsonConfig.client_code || 'DM933',
        symbol: jsonConfig.symbol === '{{ticker}}' ? 'CRUDEOIL24AUGFUT' : jsonConfig.symbol,
        exchange: jsonConfig.exchange,
        action: jsonConfig.action.includes('{{') ? 'BUY' : jsonConfig.action,
        quantity: jsonConfig.quantity.includes('{{') ? 100 : Number(jsonConfig.quantity) || 100,
        pricetype: jsonConfig.pricetype,
        product: jsonConfig.product,
      }
      if (jsonConfig.price && jsonConfig.pricetype !== 'MARKET') obj.price = Number(jsonConfig.price) || 0
      if (jsonConfig.trigger_price) obj.trigger_price = Number(jsonConfig.trigger_price) || 0
      return JSON.stringify(obj, null, 2)
    } else {
      // Indicator Mode
      const obj: any = {
        strategy: jsonConfig.strategy_tag,
        symbol: jsonConfig.symbol === '{{ticker}}' ? 'CRUDEOIL24AUGFUT' : jsonConfig.symbol,
        exchange: jsonConfig.exchange,
        action: jsonConfig.action.includes('{{') ? 'BUY' : jsonConfig.action,
        quantity: jsonConfig.quantity.includes('{{') ? 100 : Number(jsonConfig.quantity) || 100,
        pricetype: jsonConfig.pricetype,
        product: jsonConfig.product,
      }
      if (jsonConfig.price && jsonConfig.pricetype !== 'MARKET') obj.price = Number(jsonConfig.price) || 0
      if (jsonConfig.trigger_price) obj.trigger_price = Number(jsonConfig.trigger_price) || 0
      return JSON.stringify(obj, null, 2)
    }
  }

  const generatePineScriptCode = () => {
    return `//@version=5
// ==============================================================================
// OpenAlgo Multi-Account Copy Trading Webhook Alert Generator (Pine Script v5)
// ==============================================================================
// Strategy Tag : ${jsonConfig.strategy_tag}
// Exchange     : ${jsonConfig.exchange}
// Product Type : ${jsonConfig.product} (${jsonConfig.product === 'MIS' ? 'Intraday' : 'Normal / Carryforward'})
// ==============================================================================

var string OPENALGO_STRATEGY = "${jsonConfig.strategy_tag}"
var string OPENALGO_EXCHANGE = "${jsonConfig.exchange}"
var string OPENALGO_PRODUCT  = "${jsonConfig.product}"
var string OPENALGO_PRICETYPE= "${jsonConfig.pricetype}"

// Build formatted dynamic JSON alert message
f_openalgo_alert() =>
    str.format('{{\\n  "strategy": "{0}",\\n  "symbol": "{1}",\\n  "exchange": "{2}",\\n  "action": "{3}",\\n  "quantity": {4},\\n  "position_size": {5},\\n  "price": {6},\\n  "pricetype": "{7}",\\n  "product": "{8}"\\n}}',
      OPENALGO_STRATEGY,
      syminfo.ticker,
      OPENALGO_EXCHANGE,
      strategy.order.action,
      str.tostring(strategy.order.contracts),
      str.tostring(strategy.position_size),
      str.tostring(close),
      OPENALGO_PRICETYPE,
      OPENALGO_PRODUCT)

// Trigger Alert Automatically on Every Order Fill / Bar Close
if strategy.position_size != strategy.position_size[1]
    alert(f_openalgo_alert(), alert.freq_once_per_bar_close)`
  }

  const handleTestWebhookSignal = async () => {
    setTestPingRunning(true)
    setTestPingResult(null)
    try {
      let testPayload: any = {}
      if (jsonConfig.mode === 'direct_client') {
        testPayload = {
          client_code: jsonConfig.client_code || 'DM933',
          symbol: jsonConfig.symbol === '{{ticker}}' ? 'CRUDEOIL24AUGFUT' : jsonConfig.symbol,
          exchange: jsonConfig.exchange,
          action: jsonConfig.action.includes('{{') ? 'BUY' : jsonConfig.action,
          quantity: 1,
          pricetype: 'MARKET',
          product: jsonConfig.product,
        }
      } else {
        testPayload = {
          strategy: jsonConfig.strategy_tag,
          symbol: jsonConfig.symbol === '{{ticker}}' ? 'CRUDEOIL24AUGFUT' : jsonConfig.symbol,
          exchange: jsonConfig.exchange,
          action: jsonConfig.action.includes('{{') ? 'BUY' : jsonConfig.action,
          quantity: 1,
          pricetype: 'MARKET',
          product: jsonConfig.product,
        }
      }

      const res = await fetch('/api/copy-trading/webhook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(testPayload),
      })
      const data = await res.json()
      setTestPingResult({
        status: res.status,
        data,
        timestamp: new Date().toLocaleTimeString(),
      })
      if (data.status === 'success') {
        showStatus('success', `Test signal sent! Replicated to ${data.total_accounts} clients in ${data.total_latency_ms?.toFixed(1) || 15}ms`)
        fetchSummaryAndAccounts()
      } else {
        showStatus('error', data.message || 'Signal test returned notice')
      }
    } catch (e: any) {
      setTestPingResult({ status: 500, data: { error: e.message } })
      showStatus('error', `Test error: ${e.message}`)
    } finally {
      setTestPingRunning(false)
    }
  }

  // Bulk Subscriber Manager Modal State
  const [isSubscribersModalOpen, setIsSubscribersModalOpen] = useState<boolean>(false)
  const [selectedStrategyForSubscribers, setSelectedStrategyForSubscribers] = useState<Strategy | null>(null)
  const [subscriberMatrix, setSubscriberMatrix] = useState<Array<{
    account_id: number
    account_name: string
    client_code: string
    is_account_active: boolean
    connection_status: string
    last_funds: number
    is_subscribed: boolean
    multiplier: number
    fixed_qty: number
    max_daily_loss: number
  }>>([])
  const [loadingSubscribers, setLoadingSubscribers] = useState<boolean>(false)
  const [savingSubscribers, setSavingSubscribers] = useState<boolean>(false)
  const [subscriberSearchTerm, setSubscriberSearchTerm] = useState<string>('')
  const [bulkMultiplierInput, setBulkMultiplierInput] = useState<number>(1.0)

  // Telegram Alert Settings State
  const [telegramBotToken, setTelegramBotToken] = useState<string>(() => localStorage.getItem('oa_tg_token') || '')
  const [telegramChatId, setTelegramChatId] = useState<string>(() => localStorage.getItem('oa_tg_chat_id') || '')
  const [telegramTesting, setTelegramTesting] = useState<boolean>(false)

  const openSubscribersModal = async (strat: Strategy) => {
    setSelectedStrategyForSubscribers(strat)
    setIsSubscribersModalOpen(true)
    setLoadingSubscribers(true)
    try {
      const res = await fetch(`/api/copy-trading/strategies/${strat.id}/subscribers`)
      const data = await res.json()
      if (data.status === 'success') {
        setSubscriberMatrix(data.subscribers || [])
      } else {
        showStatus('error', data.message || 'Failed to fetch strategy subscribers')
      }
    } catch (e: any) {
      showStatus('error', `Error loading subscribers: ${e.message}`)
    } finally {
      setLoadingSubscribers(false)
    }
  }

  const toggleSubscriberSelection = (accountId: number) => {
    setSubscriberMatrix(prev =>
      prev.map(item => item.account_id === accountId ? { ...item, is_subscribed: !item.is_subscribed } : item)
    )
  }

  const updateSubscriberMultiplier = (accountId: number, mult: number) => {
    setSubscriberMatrix(prev =>
      prev.map(item => item.account_id === accountId ? { ...item, multiplier: mult } : item)
    )
  }

  const updateSubscriberMaxLoss = (accountId: number, loss: number) => {
    setSubscriberMatrix(prev =>
      prev.map(item => item.account_id === accountId ? { ...item, max_daily_loss: loss } : item)
    )
  }

  const handleSelectAllActiveSubscribers = () => {
    setSubscriberMatrix(prev =>
      prev.map(item => ({ ...item, is_subscribed: item.is_account_active }))
    )
    showStatus('success', 'Selected all active client accounts')
  }

  const handleDeselectAllSubscribers = () => {
    setSubscriberMatrix(prev =>
      prev.map(item => ({ ...item, is_subscribed: false }))
    )
  }

  const handleApplyGlobalMultiplierToAll = () => {
    setSubscriberMatrix(prev =>
      prev.map(item => item.is_subscribed ? { ...item, multiplier: bulkMultiplierInput } : item)
    )
    showStatus('success', `Applied ${bulkMultiplierInput}x multiplier to all selected subscribers`)
  }

  const handleSaveBulkSubscribers = async () => {
    if (!selectedStrategyForSubscribers) return
    setSavingSubscribers(true)
    try {
      const payload = {
        subscribers: subscriberMatrix.filter(s => s.is_subscribed).map(s => ({
          account_id: s.account_id,
          multiplier: s.multiplier,
          fixed_qty: s.fixed_qty || 0,
          max_daily_loss: s.max_daily_loss || 5000.0,
          is_active: true,
        })),
        replace_all: true,
      }

      const res = await fetch(`/api/copy-trading/strategies/${selectedStrategyForSubscribers.id}/bulk-subscribers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', data.message || 'Subscribers updated successfully!')
        setIsSubscribersModalOpen(false)
        fetchSummaryAndAccounts()
      } else {
        showStatus('error', data.message || 'Failed to save subscribers')
      }
    } catch (e: any) {
      showStatus('error', `Error saving subscribers: ${e.message}`)
    } finally {
      setSavingSubscribers(false)
    }
  }

  const handleQuickUpdateTimeframe = async (strategyId: number, currentTf: string) => {
    const newTf = prompt('Enter strategy timeframe (e.g. 10s, 30s, 1m, 5m, 15m, 1h, Daily):', currentTf || '10s')
    if (newTf && newTf.trim()) {
      try {
        const res = await fetch(`/api/copy-trading/strategies/update/${strategyId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ timeframe: newTf.trim() }),
        })
        const data = await res.json()
        if (data.status === 'success') {
          showStatus('success', `Strategy timeframe updated to ${newTf.trim()}!`)
          fetchSummaryAndAccounts()
        }
      } catch (e: any) {
        showStatus('error', `Failed to update timeframe: ${e.message}`)
      }
    }
  }

  const handleTestTelegram = async () => {
    setTelegramTesting(true)
    try {
      localStorage.setItem('oa_tg_token', telegramBotToken)
      localStorage.setItem('oa_tg_chat_id', telegramChatId)
      const res = await fetch('/api/copy-trading/telegram-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_token: telegramBotToken, chat_id: telegramChatId }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', 'Telegram test message delivered successfully!')
      } else {
        showStatus('error', data.message || 'Failed to send Telegram test message')
      }
    } catch (e: any) {
      showStatus('error', `Telegram test error: ${e.message}`)
    } finally {
      setTelegramTesting(false)
    }
  }

  const [savingAccount, setSavingAccount] = useState<boolean>(false)
  const [savingStrategy, setSavingStrategy] = useState<boolean>(false)
  const [syncing, setSyncing] = useState<boolean>(false)
  const [squareoffLoading, setSquareoffLoading] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const showStatus = (type: 'success' | 'error', text: string) => {
    setStatusMessage({ type, text })
    setTimeout(() => setStatusMessage(null), 5000)
  }

  const fetchSummaryAndAccounts = async () => {
    try {
      const [accRes, stratRes, readRes, feedRes] = await Promise.all([
        fetch('/api/copy-trading/accounts'),
        fetch('/api/copy-trading/strategies'),
        fetch('/api/copy-trading/readiness'),
        fetch('/api/copy-trading/feed'),
      ])

      const accData = await accRes.json()
      if (accData.status === 'success') {
        setSummary(accData.summary)
        setAccounts(accData.accounts)
      }

      const stratData = await stratRes.json()
      if (stratData.status === 'success') {
        setStrategies(stratData.strategies || [])
      }

      const readData = await readRes.json()
      if (readData.status === 'success') {
        setReadiness(readData.data)
      }

      const feedData = await feedRes.json()
      if (feedData.status === 'success') {
        setFeed(feedData.feed || [])
      }
    } catch (e) {
      console.error('Error fetching copy trading telemetry:', e)
    }
  }

  const fetchLogs = async () => {
    try {
      const res = await fetch('/api/copy-trading/orders?limit=50')
      const data = await res.json()
      if (data.status === 'success') {
        setLogs(data.orders)
      }
    } catch (e) {
      console.error('Error fetching order logs:', e)
    }
  }

  const fetchClientDetails = async (accountId: number) => {
    try {
      const res = await fetch(`/api/copy-trading/accounts/${accountId}/details`)
      const data = await res.json()
      if (data.status === 'success') {
        setClientDetails(data)
      }
    } catch (e) {
      console.error('Error fetching client details:', e)
    }
  }

  useEffect(() => {
    fetchSummaryAndAccounts()
    fetchLogs()
    const interval = setInterval(() => {
      fetchSummaryAndAccounts()
      fetchLogs()
    }, 4000)
    return () => clearInterval(interval)
  }, [])

  const handleMasterSwitchToggle = async (active: boolean) => {
    try {
      const res = await fetch('/api/copy-trading/master-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        setSummary((prev) => ({ ...prev, master_switch_active: active }))
        setReadiness((prev) => ({ ...prev, master_switch_active: active }))
        showStatus('success', data.message)
      }
    } catch (e) {
      showStatus('error', 'Failed to toggle master switch')
    }
  }

  const handleRunFireDrill = async () => {
    setFireDrillRunning(true)
    setIsFireDrillOpen(true)
    try {
      const res = await fetch('/api/copy-trading/fire-drill', { method: 'POST' })
      const data = await res.json()
      setFireDrillReport(data)
      fetchSummaryAndAccounts()
    } catch (e) {
      showStatus('error', 'Fire Drill failed to complete')
    } finally {
      setFireDrillRunning(false)
    }
  }

  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setSavingAccount(true)
    try {
      const res = await fetch('/api/copy-trading/accounts/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', data.message)
        setIsAddAccountOpen(false)
        setFormData({
          account_name: '',
          client_code: '',
          api_key: '',
          api_secret: '',
          api_key_market: '',
          api_secret_market: '',
          sizing_mode: 'MULTIPLIER',
          multiplier: 1.0,
          fixed_qty: 0,
          max_lot_cap: 50,
          max_daily_loss: 5000.0,
        })
        fetchSummaryAndAccounts()
      } else {
        showStatus('error', data.message || 'Failed to add account')
      }
    } catch (err: any) {
      showStatus('error', err.message || 'Error adding account')
    } finally {
      setSavingAccount(false)
    }
  }

  const handleAddStrategy = async (e: React.FormEvent) => {
    e.preventDefault()
    setSavingStrategy(true)
    try {
      const res = await fetch('/api/copy-trading/strategies/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(strategyFormData),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', data.message)
        setIsAddStrategyOpen(false)
        setStrategyFormData({
          strategy_tag: '',
          strategy_name: '',
          segment: 'MCXFO',
          timeframe: '1m',
          default_symbol: 'CRUDEOIL',
          description: '',
        })
        fetchSummaryAndAccounts()
      } else {
        showStatus('error', data.message || 'Failed to create strategy')
      }
    } catch (err: any) {
      showStatus('error', err.message || 'Error creating strategy')
    } finally {
      setSavingStrategy(false)
    }
  }

  const handleAssignStrategyToClient = async () => {
    if (!selectedAccountId || !assignStrategyId) return
    try {
      const res = await fetch(`/api/copy-trading/accounts/${selectedAccountId}/assign-strategy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy_id: parseInt(assignStrategyId),
          multiplier: parseFloat(assignMultiplier) || 1.0,
          max_daily_loss: parseFloat(assignMaxLoss) || 5000.0,
        }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', 'Strategy assigned to client successfully!')
        fetchClientDetails(selectedAccountId)
        fetchSummaryAndAccounts()
      } else {
        showStatus('error', data.message || 'Failed to assign strategy')
      }
    } catch (e) {
      showStatus('error', 'Error assigning strategy')
    }
  }

  const handleToggleMapping = async (mappingId: number) => {
    try {
      const res = await fetch(`/api/copy-trading/mapping/toggle/${mappingId}`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        if (selectedAccountId) fetchClientDetails(selectedAccountId)
        fetchSummaryAndAccounts()
      }
    } catch (e) {
      showStatus('error', 'Failed to toggle strategy mapping')
    }
  }

  const handleRemoveMapping = async (mappingId: number) => {
    if (!confirm('Remove this strategy assignment from the client?')) return
    try {
      const res = await fetch(`/api/copy-trading/mapping/delete/${mappingId}`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', 'Strategy removed from client')
        if (selectedAccountId) fetchClientDetails(selectedAccountId)
        fetchSummaryAndAccounts()
      }
    } catch (e) {
      showStatus('error', 'Failed to remove strategy')
    }
  }

  const handleToggleAccount = async (id: number, currentActive: boolean) => {
    try {
      const res = await fetch(`/api/copy-trading/accounts/toggle/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentActive }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        fetchSummaryAndAccounts()
        if (selectedAccountId === id) fetchClientDetails(id)
      }
    } catch (e) {
      showStatus('error', 'Failed to toggle account')
    }
  }

  const handleDeleteAccount = async (id: number, name: string) => {
    if (!confirm(`Are you sure you want to delete trading account '${name}'?`)) return
    try {
      const res = await fetch(`/api/copy-trading/accounts/delete/${id}`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', 'Account deleted successfully')
        if (selectedAccountId === id) {
          setSelectedAccountId(null)
          setClientDetails(null)
        }
        fetchSummaryAndAccounts()
      }
    } catch (e) {
      showStatus('error', 'Failed to delete account')
    }
  }

  const handleSquareOffSingleClient = async (accountId: number, clientName: string) => {
    if (!confirm(`🚨 EMERGENCY: Square off all open positions and cancel orders for ${clientName}?`)) return
    try {
      const res = await fetch(`/api/copy-trading/accounts/${accountId}/squareoff`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', `Square-off completed for ${clientName}!`)
        fetchClientDetails(accountId)
        fetchSummaryAndAccounts()
        fetchLogs()
      } else {
        showStatus('error', data.message || 'Square-off failed')
      }
    } catch (e) {
      showStatus('error', 'Square-off request failed')
    }
  }

  const handleCancelClientOrders = async (accountId: number) => {
    try {
      const res = await fetch(`/api/copy-trading/accounts/${accountId}/cancel-orders`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', data.message)
        fetchClientDetails(accountId)
      }
    } catch (e) {
      showStatus('error', 'Failed to cancel orders')
    }
  }

  const handleSyncBalances = async () => {
    setSyncing(true)
    try {
      const res = await fetch('/api/copy-trading/sync', { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', 'All account balances & PnL refreshed!')
        fetchSummaryAndAccounts()
      }
    } catch (e) {
      showStatus('error', 'Failed to sync account balances')
    } finally {
      setSyncing(false)
    }
  }

  const handleEmergencySquareOffAll = async () => {
    if (!confirm('🚨 CRITICAL ACTION: Are you sure you want to SQUARE OFF ALL positions across ALL active client accounts?')) {
      return
    }
    setSquareoffLoading(true)
    try {
      const res = await fetch('/api/copy-trading/squareoff-all', { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        showStatus('success', `Emergency Square-Off triggered across ${data.total_accounts} accounts!`)
        fetchSummaryAndAccounts()
        fetchLogs()
      } else {
        showStatus('error', data.message || 'Emergency square-off failed')
      }
    } catch (e) {
      showStatus('error', 'Emergency square-off request failed')
    } finally {
      setSquareoffLoading(false)
    }
  }

  // Filter accounts
  const filteredAccounts = accounts.filter((acc) => {
    const matchesSearch =
      acc.account_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      acc.client_code.toLowerCase().includes(searchTerm.toLowerCase())
    if (filterIssuesOnly) {
      const hasIssue = acc.connection_status !== 'connected' || (acc.last_funds || 0) < 10000 || !acc.is_active
      return matchesSearch && hasIssue
    }
    return matchesSearch
  })

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner with Master Switch */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card border rounded-xl p-5 shadow-sm">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Copy Trading & Client Hub</h1>
            <Badge variant="secondary" className="gap-1.5 py-0.5 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
              <Zap className="h-3 w-3 fill-current" />
              Symphony XTS
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Zero-latency multi-strategy trade replication across 100+ AC Agarwal accounts (MCX & NSE)
          </p>
        </div>

        {/* Action Controls & Master Switch */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Master Copy-Trading Switch */}
          <div className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg border transition-colors ${summary.master_switch_active ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-800' : 'bg-rose-50 border-rose-200 dark:bg-rose-950/40 dark:border-rose-800'}`}>
            <Power className={`h-4 w-4 ${summary.master_switch_active ? 'text-emerald-600' : 'text-rose-600'}`} />
            <span className="text-xs font-semibold">
              Copy Trading: {summary.master_switch_active ? 'ACTIVE' : 'PAUSED'}
            </span>
            <Switch
              checked={summary.master_switch_active ?? true}
              onCheckedChange={handleMasterSwitchToggle}
            />
          </div>

          <Button variant="outline" size="sm" onClick={handleRunFireDrill} className="gap-1.5 border-amber-300 text-amber-700 dark:text-amber-300 hover:bg-amber-50">
            <Flame className="h-4 w-4" />
            08:30 AM Pre-Flight Check
          </Button>

          <Button variant="outline" size="sm" onClick={handleSyncBalances} disabled={syncing} className="gap-1.5">
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            Sync Balances
          </Button>

          <Button size="sm" onClick={() => setIsAddAccountOpen(true)} className="gap-1.5">
            <UserPlus className="h-4 w-4" />
            Add Account
          </Button>

          <Button variant="destructive" size="sm" onClick={handleEmergencySquareOffAll} disabled={squareoffLoading} className="gap-1.5">
            <AlertTriangle className="h-4 w-4" />
            Square-Off All
          </Button>
        </div>
      </div>

      {/* Pre-Market Readiness Health Bar */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white rounded-xl p-4 shadow-sm border border-slate-800">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4 text-xs sm:text-sm">
            <div className="flex items-center gap-1.5 font-semibold text-slate-300">
              <Clock className="h-4 w-4 text-blue-400" />
              Pre-Market Readiness:
            </div>
            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <CheckCircle2 className="h-4 w-4" />
              {readiness.ready_count} Accounts Ready
            </div>
            <div className={`flex items-center gap-1.5 font-medium ${readiness.need_login_count > 0 ? 'text-rose-400 font-bold' : 'text-slate-400'}`}>
              <AlertCircle className="h-4 w-4" />
              {readiness.need_login_count} Need Login
            </div>
            <div className={`flex items-center gap-1.5 font-medium ${readiness.low_margin_count > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
              <AlertTriangle className="h-4 w-4" />
              {readiness.low_margin_count} Low Margin
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[11px] font-mono border-slate-700 text-slate-300 hidden sm:inline-flex">
              ⏰ Auto-Login Cron: 08:30 AM (Mon-Fri) • Telegram: ON
            </Badge>
            <Button
              variant="secondary"
              size="sm"
              className="h-7 text-xs bg-slate-700 hover:bg-slate-600 text-white"
              onClick={() => setFilterIssuesOnly(!filterIssuesOnly)}
            >
              {filterIssuesOnly ? 'Show All Accounts' : '⚡ Fix Issues Filter'}
            </Button>
          </div>
        </div>
      </div>

      {/* Status Notifications */}
      {statusMessage && (
        <div className={`p-4 rounded-lg flex items-center justify-between border ${statusMessage.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950 dark:border-emerald-800 dark:text-emerald-200' : 'bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-950 dark:border-rose-800 dark:text-rose-200'}`}>
          <div className="flex items-center gap-2 text-sm font-medium">
            {statusMessage.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
            {statusMessage.text}
          </div>
          <button onClick={() => setStatusMessage(null)} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between">
              <span>Active Accounts</span>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {summary.active_accounts} <span className="text-sm font-normal text-muted-foreground">/ {summary.total_accounts}</span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between">
              <span>Total Network Margin</span>
              <Shield className="h-4 w-4 text-muted-foreground" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">{formatCurrency(summary.total_funds)}</CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between">
              <span>Today's Combined P&L</span>
              {summary.total_pnl >= 0 ? <TrendingUp className="h-4 w-4 text-emerald-500" /> : <TrendingDown className="h-4 w-4 text-rose-500" />}
            </CardDescription>
            <CardTitle className={`text-2xl font-bold ${summary.total_pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {formatCurrency(summary.total_pnl)}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between">
              <span>Active Strategies</span>
              <Layers className="h-4 w-4 text-muted-foreground" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold">
              {strategies.filter((s) => s.is_active).length} <span className="text-sm font-normal text-muted-foreground">/ {strategies.length}</span>
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Main Tabs Navigation */}
      <Tabs defaultValue="accounts" className="space-y-4">
        <TabsList className="grid grid-cols-2 md:grid-cols-5 w-full">
          <TabsTrigger value="accounts" className="gap-2">
            <Users className="h-4 w-4" />
            Client Accounts ({accounts.length})
          </TabsTrigger>
          <TabsTrigger value="strategies" className="gap-2">
            <Layers className="h-4 w-4" />
            Strategies & Routing ({strategies.length})
          </TabsTrigger>
          <TabsTrigger value="feed" className="gap-2">
            <Activity className="h-4 w-4" />
            Plain-English Feed ({feed.length})
          </TabsTrigger>
          <TabsTrigger value="logs" className="gap-2">
            <Clock className="h-4 w-4" />
            Order Audit Logs
          </TabsTrigger>
          <TabsTrigger value="webhook" className="gap-2">
            <Code2 className="h-4 w-4" />
            Webhook & TV Alerts
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Client Accounts Table */}
        <TabsContent value="accounts" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-3">
              <div>
                <CardTitle>Configured Client Accounts</CardTitle>
                <CardDescription>Manage 100+ client credentials, inspect real-time positions, and assign strategies</CardDescription>
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <div className="relative w-full sm:w-64">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by code (DM933) or name..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-8 text-xs"
                  />
                </div>
              </div>
            </CardHeader>

            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Client Details</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Margin (Avail / Used)</TableHead>
                    <TableHead>Today's P&L</TableHead>
                    <TableHead>Trading Active</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAccounts.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                        No client accounts found matching your criteria.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredAccounts.map((acc) => (
                      <TableRow key={acc.id} className="hover:bg-muted/50 cursor-pointer" onClick={() => { setSelectedAccountId(acc.id); fetchClientDetails(acc.id); }}>
                        <TableCell>
                          <div className="font-semibold text-sm flex items-center gap-2">
                            {acc.account_name}
                            <Badge variant="outline" className="font-mono text-[11px] uppercase">
                              {acc.client_code}
                            </Badge>
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                            <span>Sizing: {acc.sizing_mode} ({acc.multiplier}x)</span>
                            <span>• Max Loss: ₹{acc.max_daily_loss.toLocaleString()}</span>
                          </div>
                        </TableCell>

                        <TableCell>
                          <Badge
                            variant={acc.connection_status === 'connected' ? 'default' : 'destructive'}
                            className={`gap-1 text-xs capitalize ${acc.connection_status === 'connected' ? 'bg-emerald-500 hover:bg-emerald-600' : ''}`}
                          >
                            {acc.connection_status === 'connected' ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                            {acc.connection_status}
                          </Badge>
                        </TableCell>

                        <TableCell>
                          <div className="font-medium text-sm">{formatCurrency(acc.last_funds || 0)}</div>
                          <div className="text-xs text-muted-foreground">
                            {(acc.last_funds || 0) < 10000 ? (
                              <span className="text-amber-600 font-semibold flex items-center gap-1">
                                <AlertTriangle className="h-3 w-3" /> Low Balance
                              </span>
                            ) : (
                              'Sufficient'
                            )}
                          </div>
                        </TableCell>

                        <TableCell>
                          <div className={`font-semibold text-sm ${acc.last_pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {formatCurrency(acc.last_pnl || 0)}
                          </div>
                        </TableCell>

                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Switch
                            checked={acc.is_active}
                            onCheckedChange={() => handleToggleAccount(acc.id, acc.is_active)}
                          />
                        </TableCell>

                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8 text-xs gap-1"
                              onClick={() => { setSelectedAccountId(acc.id); fetchClientDetails(acc.id); }}
                            >
                              <Sliders className="h-3.5 w-3.5" />
                              Inspect
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 text-xs text-rose-600 hover:bg-rose-50"
                              onClick={() => handleSquareOffSingleClient(acc.id, acc.account_name)}
                              title="Square off this client only"
                            >
                              <AlertTriangle className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-destructive"
                              onClick={() => handleDeleteAccount(acc.id, acc.account_name)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Strategies & Routing Catalog */}
        <TabsContent value="strategies" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Strategies & Routing Catalog</h2>
              <p className="text-sm text-muted-foreground">Define trading strategies and generate TradingView webhook alerts</p>
            </div>
            <Button size="sm" onClick={() => setIsAddStrategyOpen(true)} className="gap-1.5">
              <Plus className="h-4 w-4" />
              Create Strategy
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {strategies.map((strat) => (
              <Card key={strat.id} className="border shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="font-mono text-xs uppercase bg-muted">
                      {strat.strategy_tag}
                    </Badge>
                    <Badge variant={strat.is_active ? 'default' : 'secondary'} className={strat.is_active ? 'bg-emerald-500' : ''}>
                      {strat.is_active ? 'Active' : 'Paused'}
                    </Badge>
                  </div>
                  <CardTitle className="text-base font-bold mt-2">{strat.strategy_name}</CardTitle>
                  <CardDescription className="text-xs flex items-center gap-1.5 flex-wrap">
                    <span>Segment: <span className="font-semibold text-foreground">{strat.segment}</span></span>
                    <span>•</span>
                    <span>Timeframe:</span>
                    <Badge
                      variant="outline"
                      className="cursor-pointer text-[10px] font-bold text-blue-600 dark:text-blue-400 bg-blue-50/60 hover:bg-blue-100 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800"
                      title="Click to change timeframe"
                      onClick={() => handleQuickUpdateTimeframe(strat.id, strat.timeframe || '10s')}
                    >
                      {strat.timeframe || '10s'} ✏️
                    </Badge>
                  </CardDescription>
                </CardHeader>
                <CardContent className="pb-3 text-xs space-y-2">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Active Subscribers:</span>
                    <span className="font-semibold text-foreground">{strat.subscribers_count} Accounts</span>
                  </div>
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Combined Strategy P&L:</span>
                    <span className={`font-bold ${(strat.total_strategy_pnl || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {formatCurrency(strat.total_strategy_pnl || 0)}
                    </span>
                  </div>
                </CardContent>
                <CardFooter className="pt-2.5 border-t flex items-center justify-between gap-2 text-xs bg-muted/10">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs gap-1.5 font-semibold text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950/40"
                    onClick={() => openSubscribersModal(strat)}
                  >
                    <Users className="h-3.5 w-3.5" />
                    Manage Subscribers ({strat.subscribers_count})
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="h-8 text-xs gap-1.5 font-semibold"
                    onClick={() => openJsonGenerator(strat)}
                  >
                    <Code2 className="h-3.5 w-3.5 text-blue-500" />
                    View / Copy JSON
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Tab 3: Plain-English Signal Feed */}
        <TabsContent value="feed" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-blue-500" />
                Live Plain-English Execution Feed
              </CardTitle>
              <CardDescription>Human-readable replication logs showing strategy, accounts reached, and execution latency</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {feed.length === 0 ? (
                <div className="h-32 flex flex-col items-center justify-center text-muted-foreground text-sm">
                  <Sparkles className="h-8 w-8 mb-2 opacity-40" />
                  No webhook signals received yet. Waiting for incoming trades...
                </div>
              ) : (
                feed.map((item, idx) => (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-lg border flex items-start justify-between gap-3 ${item.type === 'success' ? 'bg-emerald-50/50 border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800' : 'bg-rose-50/50 border-rose-200 dark:bg-rose-950/20 dark:border-rose-800'}`}
                  >
                    <div className="flex items-start gap-3">
                      <Badge variant="outline" className="font-mono text-xs mt-0.5">
                        {item.timestamp}
                      </Badge>
                      <div>
                        <div className="text-sm font-semibold text-foreground">{item.text}</div>
                        <div className="text-xs text-muted-foreground mt-1 flex items-center gap-3">
                          <span>Strategy: <strong className="text-foreground">{item.strategy}</strong></span>
                          <span>Clients: <strong>{item.total_clients}</strong></span>
                          <span>Latency: <strong>{item.latency_ms}ms</strong></span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: Audit Order Logs */}
        <TabsContent value="logs" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Child Account Execution Logs</CardTitle>
                <CardDescription>Real-time order statuses and execution latencies across all clients</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={fetchLogs} className="gap-1 text-xs">
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </Button>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Client</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Qty</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                        No copy trade execution logs found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    logs.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="text-xs font-mono text-muted-foreground">
                          {log.created_at ? new Date(log.created_at).toLocaleTimeString() : '-'}
                        </TableCell>
                        <TableCell>
                          <div className="font-semibold text-xs">{log.account_name || 'Account'}</div>
                          <div className="text-[11px] text-muted-foreground font-mono">{log.client_code}</div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {log.strategy || 'GLOBAL'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium text-xs">{log.symbol}</TableCell>
                        <TableCell>
                          <Badge variant={log.action === 'BUY' ? 'default' : 'destructive'} className="text-[10px]">
                            {log.action}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs font-semibold">{log.quantity}</TableCell>
                        <TableCell>
                          <Badge
                            variant={log.status === 'placed' ? 'default' : 'destructive'}
                            className={`text-[10px] capitalize ${log.status === 'placed' ? 'bg-emerald-500' : ''}`}
                          >
                            {log.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs font-mono text-muted-foreground">
                          {log.execution_latency_ms ? `${log.execution_latency_ms.toFixed(1)}ms` : '-'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 5: Webhook & TV Integration */}
        <TabsContent value="webhook" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Code2 className="h-5 w-5 text-blue-500" />
                  TradingView & Python Signal Webhook Hub
                </CardTitle>
                <CardDescription>
                  Send signals to this URL to replicate trades dynamically to all subscribed clients in 15-30ms
                </CardDescription>
              </div>
              <Button
                onClick={() => setIsJsonGeneratorOpen(true)}
                className="gap-2 bg-blue-600 hover:bg-blue-700 text-xs shadow-sm"
              >
                <Code2 className="h-4 w-4" /> Open JSON Generator Wizard
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-semibold">TradingView Webhook Destination URL (Port 80 HTTP)</Label>
                  <Badge variant="outline" className="text-[10px] font-mono text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40">
                    TradingView Port 80 Compatible
                  </Badge>
                </div>
                <div className="flex gap-2">
                  <Input
                    readOnly
                    value={`${window.location.protocol}//${window.location.hostname}/api/copy-trading/webhook`}
                    className="font-mono text-xs bg-muted font-bold text-blue-600 dark:text-blue-400"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => {
                      navigator.clipboard.writeText(`${window.location.protocol}//${window.location.hostname}/api/copy-trading/webhook`)
                      showStatus('success', 'TradingView Webhook URL copied to clipboard!')
                    }}
                  >
                    <Copy className="h-4 w-4" /> Copy URL
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  TradingView requires standard Port 80 (HTTP) without custom port numbers (e.g. <code>http://168.144.22.51/api/copy-trading/webhook</code>).
                </p>
              </div>

              {/* Quick Strategy Generator Selector */}
              <div className="border rounded-lg p-4 bg-muted/30 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Live Payload for Strategy:
                  </Label>
                  <div className="flex items-center gap-2">
                    <Select
                      value={jsonConfig.strategy_tag}
                      onValueChange={(val) => {
                        const strat = strategies.find(s => s.strategy_tag === val)
                        setJsonConfig(prev => ({
                          ...prev,
                          strategy_tag: val,
                          exchange: strat?.segment || prev.exchange,
                        }))
                      }}
                    >
                      <SelectTrigger className="w-56 h-8 text-xs font-mono">
                        <SelectValue placeholder="Select Strategy" />
                      </SelectTrigger>
                      <SelectContent>
                        {strategies.map((s) => (
                          <SelectItem key={s.id} value={s.strategy_tag}>
                            {s.strategy_tag} ({s.strategy_name})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="relative">
                  <pre className="bg-slate-950 text-emerald-400 p-4 rounded-lg text-xs font-mono overflow-x-auto leading-relaxed border border-slate-800 shadow-inner">
{generateWebhookPayloadString()}
                  </pre>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="absolute top-3 right-3 h-7 text-xs gap-1 shadow bg-slate-800 text-slate-100 hover:bg-slate-700"
                    onClick={() => {
                      navigator.clipboard.writeText(generateWebhookPayloadString())
                      setCopiedPayload(true)
                      showStatus('success', 'TradingView JSON Payload copied to clipboard!')
                      setTimeout(() => setCopiedPayload(false), 2000)
                    }}
                  >
                    {copiedPayload ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedPayload ? 'Copied!' : 'Copy JSON'}
                  </Button>
                </div>
              </div>

              {/* Telegram Real-Time Alerts Configuration Card */}
              <div className="border rounded-lg p-4 bg-muted/20 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Send className="h-4 w-4 text-sky-500" />
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                        Telegram Real-Time Trade Alerts Bot
                      </h4>
                      <p className="text-[11px] text-muted-foreground">
                        Receive instant notifications on Telegram when strategy orders execute across accounts.
                      </p>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-[10px] text-sky-600 bg-sky-50 dark:bg-sky-950/30">
                    Real-Time Dispatch
                  </Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div className="space-y-1">
                    <Label className="text-xs font-semibold">Telegram Bot Token</Label>
                    <Input
                      placeholder="e.g. 123456789:ABCdefGhIJKlmNoPQRstuVWXyz"
                      value={telegramBotToken}
                      onChange={(e) => setTelegramBotToken(e.target.value)}
                      className="font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs font-semibold">Telegram Chat ID / Channel ID</Label>
                    <Input
                      placeholder="e.g. -1001234567890 or 987654321"
                      value={telegramChatId}
                      onChange={(e) => setTelegramChatId(e.target.value)}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs gap-1.5 font-semibold text-sky-600 hover:text-sky-700 hover:bg-sky-50 dark:hover:bg-sky-950/40"
                    disabled={telegramTesting || !telegramBotToken || !telegramChatId}
                    onClick={handleTestTelegram}
                  >
                    <Zap className="h-3.5 w-3.5 text-amber-500" />
                    {telegramTesting ? 'Testing...' : '⚡ Send Test Telegram Alert'}
                  </Button>
                </div>
              </div>

              {/* Step-by-Step TV Setup Card */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                <div className="p-3 border rounded-lg bg-card text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-blue-600">
                    <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700">Step 1</Badge>
                    TradingView Alert
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    Open your TradingView chart (e.g. SilverMIC or Natural Gas) and click <strong>Create Alert</strong>.
                  </p>
                </div>
                <div className="p-3 border rounded-lg bg-card text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-blue-600">
                    <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700">Step 2</Badge>
                    Notifications Tab
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    Enable <strong>Webhook URL</strong> and paste the Webhook Destination URL above.
                  </p>
                </div>
                <div className="p-3 border rounded-lg bg-card text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-blue-600">
                    <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700">Step 3</Badge>
                    Message Box
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    Clear the Alert Message box and paste the <strong>JSON Payload</strong>. Click Save.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Client Inspection Drawer / Modal */}
      {selectedAccountId && clientDetails && (
        <Dialog open={Boolean(selectedAccountId)} onOpenChange={(open) => { if (!open) setSelectedAccountId(null); }}>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader className="border-b pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <DialogTitle className="text-xl font-bold flex items-center gap-2">
                    {clientDetails.account.account_name}
                    <Badge variant="outline" className="font-mono text-xs">
                      {clientDetails.account.client_code}
                    </Badge>
                  </DialogTitle>
                  <DialogDescription className="text-xs mt-1">
                    Available Cash: <strong>{formatCurrency(clientDetails.account.last_funds || 0)}</strong> • Today's PnL:{' '}
                    <strong className={(clientDetails.account.last_pnl || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
                      {formatCurrency(clientDetails.account.last_pnl || 0)}
                    </strong>
                  </DialogDescription>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs gap-1"
                    onClick={() => window.open(`/api/copy-trading/export/client/${selectedAccountId}`, '_blank')}
                  >
                    <Download className="h-3.5 w-3.5" /> CSV Report
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="text-xs gap-1"
                    onClick={() => handleSquareOffSingleClient(clientDetails.account.id, clientDetails.account.account_name)}
                  >
                    <AlertTriangle className="h-3.5 w-3.5" /> Square-Off
                  </Button>
                </div>
              </div>
            </DialogHeader>

            <Tabs defaultValue="strategies" className="mt-3">
              <TabsList className="grid grid-cols-3 w-full">
                <TabsTrigger value="strategies" className="text-xs">
                  Assigned Strategies ({clientDetails.strategies.length})
                </TabsTrigger>
                <TabsTrigger value="positions" className="text-xs">
                  Live Positions ({clientDetails.positions.length})
                </TabsTrigger>
                <TabsTrigger value="orders" className="text-xs">
                  Open Orders ({clientDetails.open_orders.length})
                </TabsTrigger>
              </TabsList>

              {/* Subscribed Strategies */}
              <TabsContent value="strategies" className="space-y-4 pt-2">
                <div className="flex items-center gap-2 bg-muted/40 p-3 rounded-lg border">
                  <Select value={assignStrategyId} onValueChange={setAssignStrategyId}>
                    <SelectTrigger className="text-xs w-56">
                      <SelectValue placeholder="Select Strategy to Assign" />
                    </SelectTrigger>
                    <SelectContent>
                      {strategies.map((s) => (
                        <SelectItem key={s.id} value={s.id.toString()}>
                          {s.strategy_name} ({s.strategy_tag})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Input
                    placeholder="Multiplier (e.g. 2.0x)"
                    value={assignMultiplier}
                    onChange={(e) => setAssignMultiplier(e.target.value)}
                    className="text-xs w-36"
                  />

                  <Input
                    placeholder="Max Loss (Rs)"
                    value={assignMaxLoss}
                    onChange={(e) => setAssignMaxLoss(e.target.value)}
                    className="text-xs w-32"
                  />

                  <Button size="sm" onClick={handleAssignStrategyToClient} className="text-xs gap-1">
                    <Plus className="h-3.5 w-3.5" /> Assign
                  </Button>
                </div>

                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Strategy</TableHead>
                      <TableHead>Multiplier</TableHead>
                      <TableHead>Max Daily Loss</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clientDetails.strategies.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="h-20 text-center text-muted-foreground text-xs">
                          No strategies assigned yet. Select a strategy above to enroll this client.
                        </TableCell>
                      </TableRow>
                    ) : (
                      clientDetails.strategies.map((m) => (
                        <TableRow key={m.id}>
                          <TableCell className="font-semibold text-xs">
                            {m.strategy_name || m.strategy_tag}
                            <div className="text-[10px] text-muted-foreground font-mono">{m.strategy_tag}</div>
                          </TableCell>
                          <TableCell className="text-xs font-semibold">{m.multiplier}x</TableCell>
                          <TableCell className="text-xs">₹{m.max_daily_loss.toLocaleString()}</TableCell>
                          <TableCell>
                            <Switch checked={m.is_active} onCheckedChange={() => handleToggleMapping(m.id)} />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-rose-500"
                              onClick={() => handleRemoveMapping(m.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TabsContent>

              {/* Live Positions */}
              <TabsContent value="positions" className="pt-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Avg Price</TableHead>
                      <TableHead>PnL</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clientDetails.positions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="h-20 text-center text-muted-foreground text-xs">
                          No open positions for this client.
                        </TableCell>
                      </TableRow>
                    ) : (
                      clientDetails.positions.map((pos, idx) => (
                        <TableRow key={idx}>
                          <TableCell className="font-semibold text-xs">{pos.symbol}</TableCell>
                          <TableCell className="text-xs font-bold">{pos.quantity}</TableCell>
                          <TableCell className="text-xs font-mono">₹{pos.avg_price.toFixed(2)}</TableCell>
                          <TableCell className={`text-xs font-bold ${pos.pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {formatCurrency(pos.pnl)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TabsContent>

              {/* Open Orders */}
              <TabsContent value="orders" className="pt-2 space-y-3">
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs text-rose-600 gap-1"
                    onClick={() => handleCancelClientOrders(clientDetails.account.id)}
                  >
                    <StopCircle className="h-3.5 w-3.5" /> Cancel All Orders
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order ID</TableHead>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Price</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clientDetails.open_orders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="h-20 text-center text-muted-foreground text-xs">
                          No pending orders for this client.
                        </TableCell>
                      </TableRow>
                    ) : (
                      clientDetails.open_orders.map((ord) => (
                        <TableRow key={ord.order_id}>
                          <TableCell className="font-mono text-[11px]">{ord.order_id}</TableCell>
                          <TableCell className="font-semibold text-xs">{ord.symbol}</TableCell>
                          <TableCell>
                            <Badge variant={ord.action === 'BUY' ? 'default' : 'destructive'} className="text-[10px]">
                              {ord.action}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-bold">{ord.quantity}</TableCell>
                          <TableCell className="text-xs font-mono">₹{ord.price}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-[10px]">
                              {ord.status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TabsContent>
            </Tabs>
          </DialogContent>
        </Dialog>
      )}

      {/* Pre-Market Fire Drill Modal */}
      <Dialog open={isFireDrillOpen} onOpenChange={setIsFireDrillOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Flame className="h-5 w-5 text-amber-500" />
              Pre-Market Fire Drill Pre-Flight Report
            </DialogTitle>
            <DialogDescription className="text-xs">
              Zero-risk pre-market diagnostic verifying tokens, API latency, and margins across all 100+ accounts
            </DialogDescription>
          </DialogHeader>

          {fireDrillRunning ? (
            <div className="h-40 flex flex-col items-center justify-center gap-3">
              <RefreshCw className="h-8 w-8 animate-spin text-amber-500" />
              <p className="text-xs text-muted-foreground">Pinging and validating all client sessions...</p>
            </div>
          ) : fireDrillReport ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 bg-muted rounded-lg">
                  <div className="text-xs text-muted-foreground">Tested Accounts</div>
                  <div className="text-xl font-bold">{fireDrillReport.total_tested}</div>
                </div>
                <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg">
                  <div className="text-xs">100% Ready</div>
                  <div className="text-xl font-bold">{fireDrillReport.ready_count}</div>
                </div>
                <div className="p-3 bg-rose-50 text-rose-800 rounded-lg">
                  <div className="text-xs">Issues Found</div>
                  <div className="text-xl font-bold">{fireDrillReport.issue_count}</div>
                </div>
              </div>

              <div className="max-h-60 overflow-y-auto border rounded-lg p-2 space-y-1">
                {fireDrillReport.results.map((r: any) => (
                  <div key={r.account_id} className="flex items-center justify-between text-xs p-1.5 hover:bg-muted rounded">
                    <div className="flex items-center gap-2">
                      {r.ready ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-rose-500" />}
                      <span className="font-semibold">{r.account_name}</span>
                      <span className="font-mono text-muted-foreground">({r.client_code})</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span>{formatCurrency(r.funds)}</span>
                      <span className="text-muted-foreground font-mono">{r.latency_ms}ms</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button size="sm" onClick={() => setIsFireDrillOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Client Account Modal */}
      <Dialog open={isAddAccountOpen} onOpenChange={setIsAddAccountOpen}>
        <DialogContent className="max-w-lg">
          <form onSubmit={handleAddAccount}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-blue-500" />
                Add AC Agarwal Client Account
              </DialogTitle>
              <DialogDescription className="text-xs">
                Credentials are encrypted with 256-bit AES Fernet storage in SQLite.
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-3 py-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Client Name</Label>
                  <Input
                    required
                    placeholder="e.g. Rahul Sharma"
                    value={formData.account_name}
                    onChange={(e) => setFormData({ ...formData, account_name: e.target.value })}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Client Code / User ID</Label>
                  <Input
                    required
                    placeholder="e.g. DM933"
                    value={formData.client_code}
                    onChange={(e) => setFormData({ ...formData, client_code: e.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <Label>Interactive API Key</Label>
                <Input
                  required
                  placeholder="Interactive API Key"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                />
              </div>

              <div className="space-y-1">
                <Label>Interactive API Secret</Label>
                <Input
                  required
                  type="password"
                  placeholder="Interactive API Secret"
                  value={formData.api_secret}
                  onChange={(e) => setFormData({ ...formData, api_secret: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Default Multiplier</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="10.0"
                    value={formData.multiplier}
                    onChange={(e) => setFormData({ ...formData, multiplier: parseFloat(e.target.value) || 1.0 })}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Max Daily Loss (₹)</Label>
                  <Input
                    type="number"
                    value={formData.max_daily_loss}
                    onChange={(e) => setFormData({ ...formData, max_daily_loss: parseFloat(e.target.value) || 5000.0 })}
                  />
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => setIsAddAccountOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={savingAccount}>
                {savingAccount ? 'Connecting...' : 'Save & Connect'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Strategy Modal */}
      <Dialog open={isAddStrategyOpen} onOpenChange={setIsAddStrategyOpen}>
        <DialogContent className="max-w-md">
          <form onSubmit={handleAddStrategy}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5 text-blue-500" />
                Create Copy Strategy
              </DialogTitle>
              <DialogDescription className="text-xs">
                Define a strategy tag for routing TradingView webhooks to subscribed clients.
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-3 py-3 text-xs">
              <div className="space-y-1">
                <Label>Strategy Tag (Unique Key)</Label>
                <Input
                  required
                  placeholder="e.g. CRUDE_1M_SCALP"
                  value={strategyFormData.strategy_tag}
                  onChange={(e) => setStrategyFormData({ ...strategyFormData, strategy_tag: e.target.value.toUpperCase() })}
                />
              </div>

              <div className="space-y-1">
                <Label>Strategy Name</Label>
                <Input
                  required
                  placeholder="e.g. Crude Oil 1-Minute Momentum"
                  value={strategyFormData.strategy_name}
                  onChange={(e) => setStrategyFormData({ ...strategyFormData, strategy_name: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Exchange Segment</Label>
                  <Select
                    value={strategyFormData.segment}
                    onValueChange={(val) => setStrategyFormData({ ...strategyFormData, segment: val })}
                  >
                    <SelectTrigger className="text-xs">
                      <SelectValue placeholder="Segment" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MCXFO">MCXFO (Commodities)</SelectItem>
                      <SelectItem value="NSEFO">NSEFO (Index & Stock Options)</SelectItem>
                      <SelectItem value="NSECM">NSECM (Equities Cash)</SelectItem>
                      <SelectItem value="BSEFO">BSEFO (BSE Derivatives)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label>Timeframe (Custom or Quick Select)</Label>
                  <Input
                    required
                    placeholder="e.g. 10m, 30m, 1h, 15 min"
                    value={strategyFormData.timeframe}
                    onChange={(e) => setStrategyFormData({ ...strategyFormData, timeframe: e.target.value })}
                    className="text-xs font-medium"
                  />
                  <div className="flex flex-wrap gap-1 pt-1">
                    {['1m', '3m', '5m', '10m', '15m', '30m', '45m', '1h', '2h', '4h', 'Daily'].map((tf) => (
                      <Badge
                        key={tf}
                        variant={strategyFormData.timeframe === tf ? 'default' : 'outline'}
                        className="cursor-pointer text-[10px] px-1.5 py-0 hover:bg-blue-100 dark:hover:bg-blue-900"
                        onClick={() => setStrategyFormData({ ...strategyFormData, timeframe: tf })}
                      >
                        {tf}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <Label>Default Symbol</Label>
                <Input
                  required
                  placeholder="e.g. SILVERMIC, CRUDEOIL, NATURALGAS, NIFTY"
                  value={strategyFormData.default_symbol}
                  onChange={(e) => setStrategyFormData({ ...strategyFormData, default_symbol: e.target.value.toUpperCase() })}
                />
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => setIsAddStrategyOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={savingStrategy}>
                {savingStrategy ? 'Creating...' : 'Create Strategy'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Pro Interactive TradingView Alert JSON & Pine Script Studio Modal */}
      <Dialog open={isJsonGeneratorOpen} onOpenChange={setIsJsonGeneratorOpen}>
        <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto p-6">
          <DialogHeader className="border-b pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400">
                  <Code2 className="h-5 w-5" />
                </div>
                <div>
                  <DialogTitle className="text-lg font-bold">
                    TradingView Webhook & Signal Studio
                  </DialogTitle>
                  <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                    Generate dynamic, non-hardcoded JSON alerts and copy-pasteable Pine Script v5 code.
                  </DialogDescription>
                </div>
              </div>
              <Badge variant="outline" className="font-mono text-xs font-bold text-blue-600 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800 self-start sm:self-center">
                Strategy: {jsonConfig.strategy_tag}
              </Badge>
            </div>
          </DialogHeader>

          <Tabs
            value={jsonConfig.mode}
            onValueChange={(val: any) => setJsonConfig({ ...jsonConfig, mode: val })}
            className="w-full mt-2"
          >
            <TabsList className="grid grid-cols-2 sm:grid-cols-4 w-full h-auto p-1 bg-muted/60">
              <TabsTrigger value="strategy" className="text-xs py-2 gap-1.5 font-medium">
                <Zap className="h-3.5 w-3.5 text-amber-500" /> Strategy Alert
              </TabsTrigger>
              <TabsTrigger value="indicator" className="text-xs py-2 gap-1.5 font-medium">
                <BarChart3 className="h-3.5 w-3.5 text-blue-500" /> Condition Alert
              </TabsTrigger>
              <TabsTrigger value="pinescript" className="text-xs py-2 gap-1.5 font-medium">
                <Code2 className="h-3.5 w-3.5 text-emerald-500" /> Pine Script v5
              </TabsTrigger>
              <TabsTrigger value="direct_client" className="text-xs py-2 gap-1.5 font-medium">
                <Users className="h-3.5 w-3.5 text-purple-500" /> Direct Client
              </TabsTrigger>
            </TabsList>

            {/* 2-Column Responsive Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-4 text-xs">
              {/* Left Column (7 cols): Configuration Form */}
              <div className="lg:col-span-7 space-y-4">
                {/* Row 1: Target Strategy Tag / Client Code & Segment */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {jsonConfig.mode === 'direct_client' ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold">Target Client Code</Label>
                      <Input
                        placeholder="e.g. DM933"
                        value={jsonConfig.client_code}
                        onChange={(e) => setJsonConfig({ ...jsonConfig, client_code: e.target.value.toUpperCase() })}
                        className="font-mono text-xs"
                      />
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold">Target Strategy Tag</Label>
                      <Select
                        value={jsonConfig.strategy_tag}
                        onValueChange={(val) => {
                          const strat = strategies.find(s => s.strategy_tag === val)
                          setJsonConfig({
                            ...jsonConfig,
                            strategy_tag: val,
                            exchange: strat?.segment || jsonConfig.exchange,
                          })
                        }}
                      >
                        <SelectTrigger className="text-xs font-mono font-bold">
                          <SelectValue placeholder="Select Strategy" />
                        </SelectTrigger>
                        <SelectContent>
                          {strategies.map((s) => (
                            <SelectItem key={s.id} value={s.strategy_tag}>
                              {s.strategy_tag} ({s.strategy_name})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold">Exchange Segment</Label>
                    <Select
                      value={jsonConfig.exchange}
                      onValueChange={(val) => setJsonConfig({ ...jsonConfig, exchange: val })}
                    >
                      <SelectTrigger className="text-xs font-mono">
                        <SelectValue placeholder="Exchange" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="MCXFO">MCXFO (Commodities)</SelectItem>
                        <SelectItem value="NSEFO">NSEFO (NSE Futures & Options)</SelectItem>
                        <SelectItem value="NSECM">NSECM (NSE Equities Cash)</SelectItem>
                        <SelectItem value="BSEFO">BSEFO (BSE Derivatives)</SelectItem>
                        <SelectItem value="BSECM">BSECM (BSE Equities Cash)</SelectItem>
                        <SelectItem value="CDS">CDS (Currency Derivatives)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Row 2: Product Type & Price Type */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg border bg-muted/20">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-bold text-foreground">
                      Product Type (Order Mode)
                    </Label>
                    <Select
                      value={jsonConfig.product}
                      onValueChange={(val) => setJsonConfig({ ...jsonConfig, product: val })}
                    >
                      <SelectTrigger className="text-xs font-mono font-semibold">
                        <SelectValue placeholder="Product Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="MIS">MIS (Intraday with Leverage)</SelectItem>
                        <SelectItem value="NRML">NRML (Normal Carryforward F&O)</SelectItem>
                        <SelectItem value="CNC">CNC (Cash & Carry Delivery)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-bold text-foreground">
                      Execution Price Type
                    </Label>
                    <Select
                      value={jsonConfig.pricetype}
                      onValueChange={(val) => setJsonConfig({ ...jsonConfig, pricetype: val })}
                    >
                      <SelectTrigger className="text-xs font-mono font-semibold">
                        <SelectValue placeholder="Order Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="MARKET">MARKET (Immediate Market Price)</SelectItem>
                        <SelectItem value="LIMIT">LIMIT (Limit Price)</SelectItem>
                        <SelectItem value="SL-M">SL-M (Stop Loss Market)</SelectItem>
                        <SelectItem value="SL-L">SL-L (Stop Loss Limit)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Row 3: Symbol & Action */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold">Symbol / Ticker</Label>
                    <Input
                      placeholder="e.g. {{ticker}} or SILVERMIC"
                      value={jsonConfig.symbol}
                      onChange={(e) => setJsonConfig({ ...jsonConfig, symbol: e.target.value })}
                      className="font-mono text-xs"
                    />
                    <div className="flex flex-wrap gap-1 pt-1">
                      {['{{ticker}}', 'SILVERMIC', 'SILVER', 'CRUDEOIL', 'NATURALGAS', 'GOLD', 'NIFTY', 'BANKNIFTY'].map((sym) => (
                        <Badge
                          key={sym}
                          variant={jsonConfig.symbol === sym ? 'default' : 'outline'}
                          className="cursor-pointer text-[10px] px-1.5 py-0 hover:bg-muted"
                          onClick={() => setJsonConfig({ ...jsonConfig, symbol: sym })}
                        >
                          {sym}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold">Action</Label>
                    {jsonConfig.mode === 'strategy' ? (
                      <Select
                        value={jsonConfig.action}
                        onValueChange={(val) => setJsonConfig({ ...jsonConfig, action: val })}
                      >
                        <SelectTrigger className="text-xs font-mono font-bold">
                          <SelectValue placeholder="Action" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="{{strategy.order.action}}">{'{{strategy.order.action}} (Dynamic)'}</SelectItem>
                          <SelectItem value="BUY">BUY</SelectItem>
                          <SelectItem value="SELL">SELL</SelectItem>
                          <SelectItem value="SQUAREOFF">SQUAREOFF (Close Position)</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <Select
                        value={jsonConfig.action.includes('{{') ? 'BUY' : jsonConfig.action}
                        onValueChange={(val) => setJsonConfig({ ...jsonConfig, action: val })}
                      >
                        <SelectTrigger className="text-xs font-mono font-bold">
                          <SelectValue placeholder="Action" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="BUY">BUY (Long Entry / Short Exit)</SelectItem>
                          <SelectItem value="SELL">SELL (Short Entry / Long Exit)</SelectItem>
                          <SelectItem value="SQUAREOFF">SQUAREOFF (Flat Position)</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>

                {/* Row 4: Quantity & Limit Price */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold">Quantity / Multiplier Units</Label>
                    <Input
                      placeholder="e.g. {{strategy.order.contracts}} or 1"
                      value={jsonConfig.quantity}
                      onChange={(e) => setJsonConfig({ ...jsonConfig, quantity: e.target.value })}
                      className="font-mono text-xs"
                    />
                    <span className="text-[10px] text-muted-foreground">
                      Client multipliers will scale this base quantity automatically.
                    </span>
                  </div>

                  {jsonConfig.pricetype !== 'MARKET' ? (
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold">Limit Price</Label>
                      <Input
                        placeholder="{{close}} or limit price"
                        value={jsonConfig.price}
                        onChange={(e) => setJsonConfig({ ...jsonConfig, price: e.target.value })}
                        className="font-mono text-xs"
                      />
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold">Execution Price</Label>
                      <Input
                        disabled
                        value="Market Best Price ({{close}})"
                        className="font-mono text-xs bg-muted/50 text-muted-foreground"
                      />
                    </div>
                  )}
                </div>

                {/* Smart Position Sizing Switch */}
                {jsonConfig.mode === 'strategy' && (
                  <div className="flex items-center justify-between p-3 rounded-lg border bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900">
                    <div className="space-y-0.5 pr-2">
                      <div className="font-semibold text-xs text-blue-900 dark:text-blue-200 flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5 text-blue-600" />
                        Target Position Reconciliation ({'{{strategy.position_size}}'})
                      </div>
                      <div className="text-[11px] text-muted-foreground leading-tight">
                        Auto-reconciles position flips (+1 to -1) and closes (0) based on client live net positions.
                      </div>
                    </div>
                    <Switch
                      checked={jsonConfig.position_size}
                      onCheckedChange={(checked) => setJsonConfig({ ...jsonConfig, position_size: checked })}
                    />
                  </div>
                )}
              </div>

              {/* Right Column (5 cols): Live Code Output & Webhook Details */}
              <div className="lg:col-span-5 space-y-4 flex flex-col justify-between">
                {/* Code Box */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      {jsonConfig.mode === 'pinescript' ? <Code2 className="h-3.5 w-3.5 text-blue-500" /> : <FileText className="h-3.5 w-3.5 text-emerald-500" />}
                      {jsonConfig.mode === 'pinescript' ? 'Pine Script v5 Code' : 'Alert Message JSON'}
                    </Label>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1 font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40"
                      onClick={() => {
                        const content = jsonConfig.mode === 'pinescript' ? generatePineScriptCode() : generateWebhookPayloadString()
                        navigator.clipboard.writeText(content)
                        if (jsonConfig.mode === 'pinescript') setCopiedPineScript(true)
                        else setCopiedPayload(true)
                        showStatus('success', 'Copied to clipboard!')
                        setTimeout(() => {
                          setCopiedPineScript(false)
                          setCopiedPayload(false)
                        }, 2000)
                      }}
                    >
                      {(jsonConfig.mode === 'pinescript' ? copiedPineScript : copiedPayload) ? (
                        <Check className="h-3.5 w-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                      {(jsonConfig.mode === 'pinescript' ? copiedPineScript : copiedPayload) ? 'Copied!' : 'Copy Code'}
                    </Button>
                  </div>
                  <pre className="bg-slate-950 text-emerald-400 p-3.5 rounded-lg text-xs font-mono overflow-x-auto leading-relaxed border border-slate-800 shadow-inner max-h-56">
                    {jsonConfig.mode === 'pinescript' ? generatePineScriptCode() : generateWebhookPayloadString()}
                  </pre>
                </div>

                {/* Webhook Destination URL & Dry-Run Ping */}
                <div className="space-y-2 p-3 rounded-lg border bg-muted/30">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold text-foreground">TradingView Webhook URL</Label>
                    <Badge variant="outline" className="text-[10px] font-mono text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40">
                      Port 80 Ready
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      readOnly
                      value={`${window.location.protocol}//${window.location.hostname}/api/copy-trading/webhook`}
                      className="font-mono text-xs bg-muted font-bold text-blue-600 dark:text-blue-400"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1 text-xs shrink-0"
                      onClick={() => {
                        navigator.clipboard.writeText(`${window.location.protocol}//${window.location.hostname}/api/copy-trading/webhook`)
                        showStatus('success', 'TradingView Webhook URL copied!')
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" /> Copy
                    </Button>
                  </div>

                  <div className="pt-1">
                    <Button
                      variant="secondary"
                      size="sm"
                      className="w-full gap-1.5 text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-900 dark:text-amber-200 hover:bg-amber-200"
                      disabled={testPingRunning}
                      onClick={handleTestWebhookSignal}
                    >
                      <Zap className="h-3.5 w-3.5 text-amber-600" />
                      {testPingRunning ? 'Sending Simulated Signal...' : '⚡ Test Signal Ping (Dry-Run)'}
                    </Button>
                  </div>

                  {testPingResult && (
                    <div className={`p-2.5 rounded-lg border text-xs font-mono mt-2 ${testPingResult.data?.status === 'success' ? 'bg-emerald-50 border-emerald-300 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-200' : 'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-950/40 dark:border-rose-800 dark:text-rose-200'}`}>
                      <div className="font-bold flex items-center justify-between">
                        <span>Test Response ({testPingResult.status})</span>
                        <span className="text-[10px] opacity-75">{testPingResult.timestamp}</span>
                      </div>
                      <pre className="mt-1 text-[11px] whitespace-pre-wrap">
                        {JSON.stringify(testPingResult.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Tabs>

          <DialogFooter className="border-t pt-3 flex items-center justify-between sm:justify-between">
            <Button variant="outline" size="sm" onClick={() => setIsJsonGeneratorOpen(false)}>
              Close
            </Button>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                className="gap-1.5 font-semibold text-xs"
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.protocol}//${window.location.hostname}/api/copy-trading/webhook`)
                  showStatus('success', 'TradingView Webhook URL copied!')
                }}
              >
                <Copy className="h-3.5 w-3.5" /> Copy Webhook URL
              </Button>
              <Button
                size="sm"
                className="gap-1.5 bg-blue-600 hover:bg-blue-700 font-semibold text-xs"
                onClick={() => {
                  navigator.clipboard.writeText(jsonConfig.mode === 'pinescript' ? generatePineScriptCode() : generateWebhookPayloadString())
                  setCopiedPayload(true)
                  showStatus('success', 'Alert Message copied to clipboard!')
                  setTimeout(() => setCopiedPayload(false), 2000)
                }}
              >
                <Copy className="h-3.5 w-3.5" /> Copy Alert Payload
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Subscriber Management Modal (Strategy -> Clients Dual Assignment) */}
      <Dialog open={isSubscribersModalOpen} onOpenChange={setIsSubscribersModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader className="border-b pb-3">
            <div className="flex items-center justify-between">
              <div>
                <DialogTitle className="text-lg font-bold flex items-center gap-2">
                  <Users className="h-5 w-5 text-blue-500" />
                  Manage Subscribers for [{selectedStrategyForSubscribers?.strategy_tag}]
                </DialogTitle>
                <DialogDescription className="text-xs mt-1">
                  Strategy: <strong>{selectedStrategyForSubscribers?.strategy_name}</strong> • Segment: <strong>{selectedStrategyForSubscribers?.segment}</strong> • Default Symbol: <strong>{selectedStrategyForSubscribers?.default_symbol}</strong>
                </DialogDescription>
              </div>
              <Badge variant="outline" className="font-mono text-xs text-blue-600 bg-blue-50 dark:bg-blue-950/40">
                {subscriberMatrix.filter(s => s.is_subscribed).length} / {subscriberMatrix.length} Clients Subscribed
              </Badge>
            </div>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            {/* Quick Filter & Bulk Action Toolbar */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 p-3 rounded-lg border bg-muted/20">
              <div className="flex items-center gap-2 flex-1">
                <Search className="h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Filter by client name or code (e.g. DM933)..."
                  value={subscriberSearchTerm}
                  onChange={(e) => setSubscriberSearchTerm(e.target.value)}
                  className="h-8 text-xs font-medium"
                />
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs font-semibold"
                  onClick={handleSelectAllActiveSubscribers}
                >
                  Select All Active
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 text-xs"
                  onClick={handleDeselectAllSubscribers}
                >
                  Deselect All
                </Button>
                <div className="flex items-center gap-1.5 border-l pl-2">
                  <Input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="10.0"
                    value={bulkMultiplierInput}
                    onChange={(e) => setBulkMultiplierInput(parseFloat(e.target.value) || 1.0)}
                    className="h-8 w-16 text-xs font-mono text-center font-bold"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-8 text-xs font-semibold"
                    onClick={handleApplyGlobalMultiplierToAll}
                  >
                    Set Mult
                  </Button>
                </div>
              </div>
            </div>

            {/* Subscribers Matrix Table */}
            {loadingSubscribers ? (
              <div className="h-48 flex items-center justify-center text-muted-foreground text-xs">
                Loading client subscriber matrix...
              </div>
            ) : (
              <div className="border rounded-lg overflow-hidden max-h-[50vh] overflow-y-auto">
                <Table className="text-xs">
                  <TableHeader className="bg-muted/50 sticky top-0 z-10">
                    <TableRow>
                      <TableHead className="w-12 text-center">Subscribe</TableHead>
                      <TableHead>Client Account</TableHead>
                      <TableHead>Connection & Margin</TableHead>
                      <TableHead className="w-32">Multiplier</TableHead>
                      <TableHead className="w-36">Max Daily Loss (₹)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {subscriberMatrix
                      .filter(s =>
                        s.client_code.toLowerCase().includes(subscriberSearchTerm.toLowerCase()) ||
                        s.account_name.toLowerCase().includes(subscriberSearchTerm.toLowerCase())
                      )
                      .map((sub) => (
                        <TableRow
                          key={sub.account_id}
                          className={`hover:bg-muted/40 cursor-pointer ${sub.is_subscribed ? 'bg-blue-50/30 dark:bg-blue-950/20 font-medium' : 'opacity-70'}`}
                          onClick={() => toggleSubscriberSelection(sub.account_id)}
                        >
                          <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              checked={sub.is_subscribed}
                              onCheckedChange={() => toggleSubscriberSelection(sub.account_id)}
                            />
                          </TableCell>

                          <TableCell>
                            <div className="font-semibold text-foreground flex items-center gap-2">
                              {sub.account_name}
                              <Badge variant="outline" className="font-mono text-[10px]">
                                {sub.client_code}
                              </Badge>
                            </div>
                            <div className="text-[11px] text-muted-foreground">
                              Status: {sub.is_account_active ? 'Active' : 'Disabled'}
                            </div>
                          </TableCell>

                          <TableCell>
                            <div className="font-medium">{formatCurrency(sub.last_funds || 0)}</div>
                            <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                              <span className={`h-1.5 w-1.5 rounded-full ${sub.connection_status === 'connected' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                              {sub.connection_status}
                            </div>
                          </TableCell>

                          <TableCell onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center gap-1">
                              <Input
                                type="number"
                                step="0.1"
                                min="0.1"
                                max="10.0"
                                disabled={!sub.is_subscribed}
                                value={sub.multiplier}
                                onChange={(e) => updateSubscriberMultiplier(sub.account_id, parseFloat(e.target.value) || 1.0)}
                                className="h-7 text-xs font-mono font-bold"
                              />
                              <span className="text-[11px] text-muted-foreground font-mono">x</span>
                            </div>
                          </TableCell>

                          <TableCell onClick={(e) => e.stopPropagation()}>
                            <Input
                              type="number"
                              step="500"
                              min="0"
                              disabled={!sub.is_subscribed}
                              value={sub.max_daily_loss}
                              onChange={(e) => updateSubscriberMaxLoss(sub.account_id, parseFloat(e.target.value) || 5000.0)}
                              className="h-7 text-xs font-mono"
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>

          <DialogFooter className="border-t pt-3 flex items-center justify-between sm:justify-between">
            <Button variant="outline" size="sm" onClick={() => setIsSubscribersModalOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="gap-1.5 bg-blue-600 hover:bg-blue-700 font-semibold"
              disabled={savingSubscribers}
              onClick={handleSaveBulkSubscribers}
            >
              <Check className="h-4 w-4" />
              {savingSubscribers ? 'Saving Subscribers...' : `Save Subscribers (${subscriberMatrix.filter(s => s.is_subscribed).length} Clients)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
