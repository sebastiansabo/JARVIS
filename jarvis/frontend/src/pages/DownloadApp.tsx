import { Download, Smartphone, Share2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const APK_URL = `${window.location.origin}/download/jarvis.apk`
const QR_IMG = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(APK_URL)}&format=png`

export default function DownloadApp() {
  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: 'JARVIS Mobile',
          text: 'Download JARVIS Mobile App',
          url: APK_URL,
        })
      } catch {
        // user cancelled
      }
    } else {
      await navigator.clipboard.writeText(APK_URL)
      alert('Link copied to clipboard!')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Download Mobile App</h1>
        <p className="text-sm text-muted-foreground">Share the JARVIS mobile app with your team</p>
      </div>

      <div className="flex justify-center">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6 flex flex-col items-center gap-6">
            {/* App icon */}
            <div className="h-20 w-20 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
              <Smartphone className="h-10 w-10 text-white" />
            </div>

            <div className="text-center">
              <h2 className="text-xl font-bold">JARVIS Mobile</h2>
              <p className="text-sm text-muted-foreground mt-1">Android App v1.0.0</p>
            </div>

            {/* QR Code */}
            <div className="bg-white rounded-2xl p-4">
              <img
                src={QR_IMG}
                alt="QR Code to download JARVIS Mobile"
                width={250}
                height={250}
                className="block"
              />
            </div>

            <p className="text-sm text-muted-foreground text-center">
              Scan the QR code with your phone camera to download
            </p>

            {/* Action buttons */}
            <div className="flex gap-3 w-full">
              <Button asChild className="flex-1">
                <a href={APK_URL} download>
                  <Download className="mr-2 h-4 w-4" />
                  Download APK
                </a>
              </Button>
              <Button variant="outline" onClick={handleShare}>
                <Share2 className="mr-2 h-4 w-4" />
                Share
              </Button>
            </div>

            {/* Install instructions */}
            <div className="w-full border-t pt-4">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Installation Steps</h3>
              <ol className="text-sm text-muted-foreground space-y-2 list-decimal list-inside">
                <li>Download the APK file on your Android device</li>
                <li>Open the downloaded file</li>
                <li>Allow "Install from unknown sources" if prompted</li>
                <li>Tap Install and open JARVIS</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
