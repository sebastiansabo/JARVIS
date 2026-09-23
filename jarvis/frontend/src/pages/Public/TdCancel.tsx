import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { tdApi } from '@/api/td'
import { ApiError } from '@/api/client'

export default function TdCancel() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<'idle' | 'ok' | 'gone' | 'err'>('idle')
  const m = useMutation({
    mutationFn: () => tdApi.cancel(token),
    onSuccess: () => setState('ok'),
    onError: (e) => setState(e instanceof ApiError && e.status === 410 ? 'gone' : 'err'),
  })
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center">
      <div>
        {state === 'idle' && <>
          <h1 className="text-2xl font-bold">Anulează programarea</h1>
          <button className="mt-4 bg-black text-white rounded px-6 py-2"
                  disabled={!token || m.isPending} onClick={() => m.mutate()}>Anulează test drive</button>
        </>}
        {state === 'ok' && <h1 className="text-2xl font-bold">Programare anulată.</h1>}
        {state === 'gone' && <h1 className="text-2xl font-bold">Linkul a expirat.</h1>}
        {state === 'err' && <h1 className="text-2xl font-bold">A apărut o eroare.</h1>}
      </div>
    </div>
  )
}
