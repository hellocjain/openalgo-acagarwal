import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Plus,
  RefreshCw,
  Trash2,
  Users,
  XCircle,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
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
  })
  const [accounts, setAccounts] = useState<ChildAccount[]>([])
  const [orders, setOrders] = useState<CopyOrderLog[]>([])
  const [syncing, setSyncing] = useState<boolean>(false)
  const [squareoffLoading, setSquareoffLoading] = useState<boolean>(false)

  // Dialog States
  const [isAddOpen, setIsAddOpen] = useState<boolean>(false)
  const [isSquareoffConfirmOpen, setIsSquareoffConfirmOpen] = useState<boolean>(false)

  // Form States
  const [formData, setFormData] = useState({
    account_name: '',
    client_code: '',
    api_key: '',
    api_secret: '',
    sizing_mode: 'MULTIPLIER',
    multiplier: '1.0',
    fixed_qty: '0',
    max_lot_cap: '50',
    max_daily_loss: '5000',
  })
  const [formSubmitting, setFormSubmitting] = useState<boolean>(false)
  const [formError, setFormError] = useState<string>('')

  const fetchAccounts = async () => {
    try {
      const res = await fetch('/api/copy-trading/accounts')
      const data = await res.json()
      if (data.status === 'success') {
        setSummary(data.summary || {})
        setAccounts(data.accounts || [])
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err)
    }
  }

  const fetchOrders = async () => {
    try {
      const res = await fetch('/api/copy-trading/orders?limit=50')
      const data = await res.json()
      if (data.status === 'success') {
        setOrders(data.orders || [])
      }
    } catch (err) {
      console.error('Failed to fetch orders:', err)
    }
  }

  useEffect(() => {
    fetchAccounts()
    fetchOrders()
    const interval = setInterval(() => {
      fetchAccounts()
      fetchOrders()
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleSyncTelemetry = async () => {
    setSyncing(true)
    try {
      await fetch('/api/copy-trading/accounts/sync', { method: 'POST' })
      await fetchAccounts()
    } catch (err) {
      console.error('Failed to sync telemetry:', err)
    } finally {
      setSyncing(false)
    }
  }

  const handleToggleAccount = async (id: number, currentStatus: boolean) => {
    try {
      await fetch(`/api/copy-trading/accounts/toggle/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentStatus }),
      })
      fetchAccounts()
    } catch (err) {
      console.error('Failed to toggle account:', err)
    }
  }

  const handleDeleteAccount = async (id: number) => {
    if (!window.confirm('Are you sure you want to remove this client account?')) return
    try {
      await fetch(`/api/copy-trading/accounts/delete/${id}`, { method: 'POST' })
      fetchAccounts()
    } catch (err) {
      console.error('Failed to delete account:', err)
    }
  }

  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormSubmitting(true)
    setFormError('')

    try {
      const res = await fetch('/api/copy-trading/accounts/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_name: formData.account_name,
          client_code: formData.client_code,
          api_key: formData.api_key,
          api_secret: formData.api_secret,
          sizing_mode: formData.sizing_mode,
          multiplier: parseFloat(formData.multiplier) || 1.0,
          fixed_qty: parseInt(formData.fixed_qty) || 0,
          max_lot_cap: parseInt(formData.max_lot_cap) || 50,
          max_daily_loss: parseFloat(formData.max_daily_loss) || 5000,
        }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        setIsAddOpen(false)
        setFormData({
          account_name: '',
          client_code: '',
          api_key: '',
          api_secret: '',
          sizing_mode: 'MULTIPLIER',
          multiplier: '1.0',
          fixed_qty: '0',
          max_lot_cap: '50',
          max_daily_loss: '5000',
        })
        fetchAccounts()
      } else {
        setFormError(data.message || 'Failed to add account')
      }
    } catch (err: any) {
      setFormError(err.message || 'Network error')
    } finally {
      setFormSubmitting(false)
    }
  }

  const handleEmergencySquareOff = async () => {
    setSquareoffLoading(true)
    try {
      await fetch('/api/copy-trading/squareoff-all', { method: 'POST' })
      setIsSquareoffConfirmOpen(false)
      fetchAccounts()
      fetchOrders()
    } catch (err) {
      console.error('Squareoff failed:', err)
    } finally {
      setSquareoffLoading(false)
    }
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-2">
            <Users className="w-7 h-7 text-primary" />
            Copy Trading Multi-Account Hub
          </h1>
          <p className="text-sm text-muted-foreground">
            Zero-latency trade replication across all AC Agarwal client accounts
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncTelemetry}
            disabled={syncing}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            Sync Balances
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={() => setIsAddOpen(true)}
            className="flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Add Client Account
          </Button>

          <Button
            variant="destructive"
            size="sm"
            onClick={() => setIsSquareoffConfirmOpen(true)}
            className="flex items-center gap-1.5 shadow-sm"
          >
            <AlertTriangle className="w-4 h-4" />
            Square-Off All
          </Button>
        </div>
      </div>

      {/* Telemetry KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Active Accounts</CardDescription>
            <CardTitle className="text-xl sm:text-2xl font-bold">
              {summary.active_accounts} / {summary.total_accounts}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Total Network Margin</CardDescription>
            <CardTitle className="text-xl sm:text-2xl font-bold">
              {formatCurrency(summary.total_funds)}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Today's Combined P&L</CardDescription>
            <CardTitle
              className={`text-xl sm:text-2xl font-bold ${
                summary.total_pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}
            >
              {formatCurrency(summary.total_pnl)}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">Broker Protocol</CardDescription>
            <CardTitle className="text-xl sm:text-2xl font-bold flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
              <Zap className="w-5 h-5" />
              Symphony XTS
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Main Tabs */}
      <Tabs defaultValue="accounts" className="space-y-4">
        <TabsList>
          <TabsTrigger value="accounts">Client Accounts ({accounts.length})</TabsTrigger>
          <TabsTrigger value="orders">Copy Order Logs ({orders.length})</TabsTrigger>
          <TabsTrigger value="webhook">Webhook & Integration</TabsTrigger>
        </TabsList>

        {/* Tab 1: Client Accounts Table */}
        <TabsContent value="accounts" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Configured Client Accounts</CardTitle>
              <CardDescription>
                Manage active client accounts, customize lot multipliers, and monitor real-time P&L.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {accounts.length === 0 ? (
                <div className="text-center py-12 space-y-3">
                  <Users className="w-12 h-12 mx-auto text-muted-foreground opacity-50" />
                  <h3 className="text-base font-semibold">No Client Accounts Added Yet</h3>
                  <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                    Click "Add Client Account" above to link your first AC Agarwal trading account.
                  </p>
                  <Button onClick={() => setIsAddOpen(true)} size="sm">
                    <Plus className="w-4 h-4 mr-1.5" />
                    Add First Account
                  </Button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Client / Account</TableHead>
                        <TableHead>Client Code</TableHead>
                        <TableHead>Sizing Rule</TableHead>
                        <TableHead>Available Margin</TableHead>
                        <TableHead>Today's P&L</TableHead>
                        <TableHead>Connection</TableHead>
                        <TableHead>Active</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accounts.map((acc) => (
                        <TableRow key={acc.id}>
                          <TableCell className="font-medium">
                            {acc.account_name}
                            {acc.is_primary && (
                              <Badge variant="outline" className="ml-2 text-[10px]">
                                Master
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="font-mono">{acc.client_code}</TableCell>
                          <TableCell>
                            <Badge variant="secondary" className="font-normal">
                              {acc.sizing_mode === 'MULTIPLIER' && `${acc.multiplier}x Multiplier`}
                              {acc.sizing_mode === 'FIXED_LOTS' && `${acc.fixed_qty} Fixed Qty`}
                              {acc.sizing_mode === 'CAPITAL_RATIO' && 'Capital Ratio'}
                            </Badge>
                          </TableCell>
                          <TableCell>{formatCurrency(acc.last_funds)}</TableCell>
                          <TableCell
                            className={`font-semibold ${
                              acc.last_pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {formatCurrency(acc.last_pnl)}
                          </TableCell>
                          <TableCell>
                            {acc.connection_status === 'connected' ? (
                              <Badge variant="outline" className="text-green-600 border-green-500 bg-green-500/10 flex items-center gap-1 w-fit">
                                <CheckCircle2 className="w-3 h-3" />
                                Live
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-red-600 border-red-500 bg-red-500/10 flex items-center gap-1 w-fit">
                                <XCircle className="w-3 h-3" />
                                {acc.connection_status}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <Switch
                              checked={acc.is_active}
                              onCheckedChange={() => handleToggleAccount(acc.id, acc.is_active)}
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDeleteAccount(acc.id)}
                              className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Copy Order Logs */}
        <TabsContent value="orders" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Recent Multi-Account Execution Logs</CardTitle>
              <CardDescription>
                Detailed audit trail of signals replicated across child accounts with individual latency.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {orders.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No copy trading orders recorded yet.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Client Account</TableHead>
                        <TableHead>Symbol</TableHead>
                        <TableHead>Action</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead>Type / Product</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Latency</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {orders.map((ord) => (
                        <TableRow key={ord.id}>
                          <TableCell className="text-xs text-muted-foreground">
                            {ord.created_at ? new Date(ord.created_at).toLocaleTimeString() : '-'}
                          </TableCell>
                          <TableCell className="font-medium">
                            {ord.account_name} ({ord.client_code})
                          </TableCell>
                          <TableCell className="font-mono">{ord.symbol}</TableCell>
                          <TableCell>
                            <Badge
                              variant={ord.action === 'BUY' ? 'default' : 'destructive'}
                              className="text-[10px]"
                            >
                              {ord.action}
                            </Badge>
                          </TableCell>
                          <TableCell>{ord.quantity}</TableCell>
                          <TableCell className="text-xs">
                            {ord.pricetype} / {ord.product}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={
                                ord.status === 'placed'
                                  ? 'text-green-600 border-green-500 bg-green-500/10'
                                  : 'text-red-600 border-red-500 bg-red-500/10'
                              }
                            >
                              {ord.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {ord.execution_latency_ms ? `${ord.execution_latency_ms.toFixed(1)}ms` : '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Webhook Integration Guide */}
        <TabsContent value="webhook" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">TradingView & Strategy Webhook Ingestion</CardTitle>
              <CardDescription>
                Point your TradingView alerts or Python algorithms to this single endpoint to replicate trades across all active accounts.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="text-xs font-semibold">Copy Trading Webhook URL</Label>
                <div className="flex items-center gap-2 mt-1.5">
                  <Input
                    readOnly
                    value={`${window.location.origin}/api/copy-trading/webhook`}
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      navigator.clipboard.writeText(`${window.location.origin}/api/copy-trading/webhook`)
                      alert('Webhook URL copied to clipboard!')
                    }}
                  >
                    <Copy className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              <div>
                <Label className="text-xs font-semibold">Example JSON Webhook Payload</Label>
                <pre className="mt-1.5 p-4 rounded-lg bg-muted font-mono text-xs overflow-x-auto">
{`{
  "strategy": "NIFTY_MOMENTUM",
  "symbol": "NIFTY28AUG2424500CE",
  "exchange": "NFO",
  "action": "BUY",
  "quantity": 25,
  "pricetype": "MARKET",
  "product": "MIS"
}`}
                </pre>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Add Client Account Dialog */}
      <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Add AC Agarwal Client Account</DialogTitle>
            <DialogDescription>
              Link a new child trading account. Credentials will be securely encrypted with Fernet 256-bit encryption.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleAddAccount} className="space-y-4 py-2">
            {formError && (
              <div className="p-3 text-xs rounded-md bg-destructive/15 text-destructive border border-destructive/20">
                {formError}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="account_name">Client Name</Label>
                <Input
                  id="account_name"
                  required
                  placeholder="e.g. Rahul Sharma"
                  value={formData.account_name}
                  onChange={(e) => setFormData({ ...formData, account_name: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="client_code">Client Code / User ID</Label>
                <Input
                  id="client_code"
                  required
                  placeholder="e.g. DM933"
                  value={formData.client_code}
                  onChange={(e) => setFormData({ ...formData, client_code: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="api_key">Interactive API Key (BROKER_API_KEY)</Label>
              <Input
                id="api_key"
                required
                placeholder="Enter Interactive API Key"
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="api_secret">Interactive API Secret (BROKER_API_SECRET)</Label>
              <Input
                id="api_secret"
                type="password"
                required
                placeholder="Enter Interactive API Secret"
                value={formData.api_secret}
                onChange={(e) => setFormData({ ...formData, api_secret: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Sizing Mode</Label>
                <Select
                  value={formData.sizing_mode}
                  onValueChange={(val) => setFormData({ ...formData, sizing_mode: val })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="MULTIPLIER">Multiplier (Proportional)</SelectItem>
                    <SelectItem value="FIXED_LOTS">Fixed Quantity</SelectItem>
                    <SelectItem value="CAPITAL_RATIO">Capital Ratio</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="multiplier">Multiplier</Label>
                <Input
                  id="multiplier"
                  type="number"
                  step="0.1"
                  min="0.1"
                  value={formData.multiplier}
                  onChange={(e) => setFormData({ ...formData, multiplier: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="max_lot_cap">Max Lot Cap</Label>
                <Input
                  id="max_lot_cap"
                  type="number"
                  value={formData.max_lot_cap}
                  onChange={(e) => setFormData({ ...formData, max_lot_cap: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="max_daily_loss">Max Daily Loss (₹)</Label>
                <Input
                  id="max_daily_loss"
                  type="number"
                  value={formData.max_daily_loss}
                  onChange={(e) => setFormData({ ...formData, max_daily_loss: e.target.value })}
                />
              </div>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" onClick={() => setIsAddOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={formSubmitting}>
                {formSubmitting ? 'Verifying & Saving...' : 'Save & Connect'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Emergency Square-Off Confirmation Dialog */}
      <Dialog open={isSquareoffConfirmOpen} onOpenChange={setIsSquareoffConfirmOpen}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="w-5 h-5" />
              Emergency Square-Off All Accounts?
            </DialogTitle>
            <DialogDescription>
              This will immediately cancel all open pending orders and place MARKET exit orders for all open positions across all active child accounts. This action is irreversible.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setIsSquareoffConfirmOpen(false)}
              disabled={squareoffLoading}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleEmergencySquareOff}
              disabled={squareoffLoading}
            >
              {squareoffLoading ? 'Closing All Positions...' : 'Yes, Square-Off All'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
