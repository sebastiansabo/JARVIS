import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { tdApi } from '@/api/td'
import { ApiError } from '@/api/client'

export default function TdConfirm() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<'idle' | 'ok' | 'gone' | 'conflict' | 'err'>('idle')
  const m = useMutation({
    mutationFn: () => tdApi.confirm(token),
    onSuccess: () => setState('ok'),
    onError: (e) => setState(e instanceof ApiError && e.status === 409 ? 'conflict'
      : e instanceof ApiError && e.status === 410 ? 'gone' : 'err'),
  })
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center">
      <div>
        {state === 'idle' && <>
          <h1 className="text-2xl font-bold">Confirmă programarea</h1>
          <button className="mt-4 bg-black text-white rounded px-6 py-2"
                  disabled={!token || m.isPending} onClick={() => m.mutate()}>Confirmă test drive</button>
        </>}
        {state === 'ok' && <h1 className="text-2xl font-bold text-green-600">Programare confirmată! Ne vedem la eveniment.</h1>}
        {state === 'gone' && <h1 className="text-2xl font-bold">Linkul a expirat sau a fost deja folosit.</h1>}
        {state === 'conflict' && <h1 className="text-2xl font-bold">Ne pare rău, mașina nu mai este disponibilă pentru acest interval.</h1>}
        {state === 'err' && <h1 className="text-2xl font-bold">A apărut o eroare. Încearcă din nou.</h1>}
      </div>
    </div>
  )
}
