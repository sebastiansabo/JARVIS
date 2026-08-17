/** Dial-code options for the Test Drive "new client" phone field — European
 *  countries only, România first (the default), the rest alphabetical. The UI
 *  shows just the flag + code, so a foreign client's number is stored as E.164. */
export const COUNTRY_DIAL_CODES: { code: string; country: string; flag: string }[] = [
  { code: '+40', country: 'România', flag: '🇷🇴' },
  { code: '+355', country: 'Albania', flag: '🇦🇱' },
  { code: '+376', country: 'Andorra', flag: '🇦🇩' },
  { code: '+43', country: 'Austria', flag: '🇦🇹' },
  { code: '+32', country: 'Belgia', flag: '🇧🇪' },
  { code: '+375', country: 'Bielorusia', flag: '🇧🇾' },
  { code: '+387', country: 'Bosnia și Herțegovina', flag: '🇧🇦' },
  { code: '+359', country: 'Bulgaria', flag: '🇧🇬' },
  { code: '+420', country: 'Cehia', flag: '🇨🇿' },
  { code: '+357', country: 'Cipru', flag: '🇨🇾' },
  { code: '+385', country: 'Croația', flag: '🇭🇷' },
  { code: '+45', country: 'Danemarca', flag: '🇩🇰' },
  { code: '+41', country: 'Elveția', flag: '🇨🇭' },
  { code: '+372', country: 'Estonia', flag: '🇪🇪' },
  { code: '+358', country: 'Finlanda', flag: '🇫🇮' },
  { code: '+33', country: 'Franța', flag: '🇫🇷' },
  { code: '+49', country: 'Germania', flag: '🇩🇪' },
  { code: '+30', country: 'Grecia', flag: '🇬🇷' },
  { code: '+353', country: 'Irlanda', flag: '🇮🇪' },
  { code: '+354', country: 'Islanda', flag: '🇮🇸' },
  { code: '+39', country: 'Italia', flag: '🇮🇹' },
  { code: '+383', country: 'Kosovo', flag: '🇽🇰' },
  { code: '+371', country: 'Letonia', flag: '🇱🇻' },
  { code: '+423', country: 'Liechtenstein', flag: '🇱🇮' },
  { code: '+370', country: 'Lituania', flag: '🇱🇹' },
  { code: '+352', country: 'Luxemburg', flag: '🇱🇺' },
  { code: '+389', country: 'Macedonia de Nord', flag: '🇲🇰' },
  { code: '+356', country: 'Malta', flag: '🇲🇹' },
  { code: '+44', country: 'Marea Britanie', flag: '🇬🇧' },
  { code: '+373', country: 'Moldova', flag: '🇲🇩' },
  { code: '+377', country: 'Monaco', flag: '🇲🇨' },
  { code: '+382', country: 'Muntenegru', flag: '🇲🇪' },
  { code: '+47', country: 'Norvegia', flag: '🇳🇴' },
  { code: '+31', country: 'Olanda', flag: '🇳🇱' },
  { code: '+48', country: 'Polonia', flag: '🇵🇱' },
  { code: '+351', country: 'Portugalia', flag: '🇵🇹' },
  { code: '+7', country: 'Rusia', flag: '🇷🇺' },
  { code: '+378', country: 'San Marino', flag: '🇸🇲' },
  { code: '+381', country: 'Serbia', flag: '🇷🇸' },
  { code: '+421', country: 'Slovacia', flag: '🇸🇰' },
  { code: '+386', country: 'Slovenia', flag: '🇸🇮' },
  { code: '+34', country: 'Spania', flag: '🇪🇸' },
  { code: '+46', country: 'Suedia', flag: '🇸🇪' },
  { code: '+380', country: 'Ucraina', flag: '🇺🇦' },
  { code: '+36', country: 'Ungaria', flag: '🇭🇺' },
]

/** Combine a dial code with a locally-typed number into an E.164 string.
 *  Strips spaces/dashes and a single trunk `0` (so `0721…` and `721…` both
 *  work), then validates the result is a plausible E.164 number. */
export function composePhone(dialCode: string, rawNumber: string): { full: string; valid: boolean } {
  const local = rawNumber.replace(/[\s-]/g, '').replace(/^0/, '')
  const full = local ? `${dialCode}${local}` : ''
  const valid = /^\d{6,14}$/.test(local) && /^\+\d{7,15}$/.test(full)
  return { full, valid }
}
