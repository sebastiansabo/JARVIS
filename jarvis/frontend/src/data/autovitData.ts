/**
 * Autovit-compatible predefined field values.
 *
 * All enum values match the Autovit / OLX Auto API format
 * so publishing to Autovit requires zero mapping.
 */

// ── Brands ──────────────────────────────────────────────────

export const AUTOVIT_BRANDS = [
  'Abarth', 'Acura', 'Aiways', 'Alfa Romeo', 'Alpine', 'Aston Martin',
  'Audi', 'Bentley', 'BMW', 'Bugatti', 'Buick', 'BYD', 'Cadillac',
  'Caterham', 'Chevrolet', 'Chrysler', 'Citroen', 'Cupra', 'Dacia',
  'Daewoo', 'Daihatsu', 'DFSK', 'Dodge', 'DS', 'Ferrari', 'Fiat',
  'Ford', 'Genesis', 'GMC', 'Great Wall', 'Honda', 'Hummer', 'Hyundai',
  'Infiniti', 'Isuzu', 'Iveco', 'Jaguar', 'Jeep', 'Kia', 'KTM',
  'Lada', 'Lamborghini', 'Lancia', 'Land Rover', 'Lexus', 'Lincoln',
  'Lotus', 'Maserati', 'Maybach', 'Mazda', 'McLaren', 'Mercedes-Benz',
  'MG', 'MINI', 'Mitsubishi', 'Morgan', 'Nissan', 'Opel', 'Peugeot',
  'Polestar', 'Pontiac', 'Porsche', 'Renault', 'Rolls-Royce', 'Rover',
  'Saab', 'SEAT', 'Skoda', 'Smart', 'SsangYong', 'Subaru', 'Suzuki',
  'Tesla', 'Toyota', 'Trabant', 'Volkswagen', 'Volvo', 'Wartburg',
] as const

// ── Models per brand ────────────────────────────────────────

export const AUTOVIT_MODELS: Record<string, string[]> = {
  'Abarth': ['124 Spider', '500', '500e', '595', '695', 'Punto'],
  'Alfa Romeo': ['147', '156', '159', '166', '4C', 'Brera', 'Giulia', 'Giulietta', 'GT', 'GTV', 'MiTo', 'Spider', 'Stelvio', 'Tonale'],
  'Audi': ['A1', 'A2', 'A3', 'A4', 'A4 Allroad', 'A5', 'A6', 'A6 Allroad', 'A7', 'A8', 'e-tron', 'e-tron GT', 'Q2', 'Q3', 'Q4 e-tron', 'Q5', 'Q5 Sportback', 'Q7', 'Q8', 'Q8 e-tron', 'R8', 'RS3', 'RS4', 'RS5', 'RS6', 'RS7', 'RS Q3', 'RS Q8', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'SQ5', 'SQ7', 'SQ8', 'TT', 'TTS'],
  'BMW': ['Seria 1', 'Seria 2', 'Seria 2 Active Tourer', 'Seria 2 Gran Coupe', 'Seria 3', 'Seria 3 GT', 'Seria 4', 'Seria 4 Gran Coupe', 'Seria 5', 'Seria 5 GT', 'Seria 6', 'Seria 6 GT', 'Seria 7', 'Seria 8', 'i3', 'i4', 'i5', 'i7', 'iX', 'iX1', 'iX2', 'iX3', 'M2', 'M3', 'M4', 'M5', 'M8', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'XM', 'Z3', 'Z4'],
  'BYD': ['Atto 3', 'Dolphin', 'Han', 'Seal', 'Seal U', 'Tang'],
  'Chevrolet': ['Aveo', 'Camaro', 'Captiva', 'Corvette', 'Cruze', 'Equinox', 'Malibu', 'Orlando', 'Spark', 'Tahoe', 'Trax'],
  'Citroen': ['Berlingo', 'C1', 'C3', 'C3 Aircross', 'C4', 'C4 Cactus', 'C4 X', 'C5', 'C5 Aircross', 'C5 X', 'DS3', 'DS4', 'DS5', 'Jumpy', 'SpaceTourer', 'e-C4'],
  'Cupra': ['Ateca', 'Born', 'Formentor', 'Leon', 'Tavascan', 'Terramar'],
  'Dacia': ['Dokker', 'Duster', 'Jogger', 'Lodgy', 'Logan', 'Logan MCV', 'Sandero', 'Sandero Stepway', 'Spring'],
  'DS': ['DS 3', 'DS 3 Crossback', 'DS 4', 'DS 5', 'DS 7', 'DS 7 Crossback', 'DS 9'],
  'Ferrari': ['296 GTB', '296 GTS', '488', '812', 'California', 'F8', 'GTC4Lusso', 'Portofino', 'Purosangue', 'Roma', 'SF90'],
  'Fiat': ['124 Spider', '500', '500C', '500e', '500L', '500X', '600e', 'Bravo', 'Doblo', 'Ducato', 'Grande Punto', 'Panda', 'Punto', 'Tipo'],
  'Ford': ['B-Max', 'C-Max', 'Capri', 'EcoSport', 'Edge', 'Explorer', 'Fiesta', 'Focus', 'Galaxy', 'Ka', 'Kuga', 'Maverick', 'Mondeo', 'Mustang', 'Mustang Mach-E', 'Puma', 'Ranger', 'S-Max', 'Tourneo Connect', 'Tourneo Custom', 'Transit', 'Transit Connect', 'Transit Custom'],
  'Genesis': ['G70', 'G80', 'G90', 'GV60', 'GV70', 'GV80'],
  'Honda': ['Accord', 'Civic', 'CR-V', 'e:Ny1', 'HR-V', 'Jazz', 'ZR-V'],
  'Hyundai': ['Bayon', 'Elantra', 'Getz', 'i10', 'i20', 'i30', 'i40', 'Ioniq', 'Ioniq 5', 'Ioniq 6', 'ix20', 'ix35', 'Kona', 'Nexo', 'Santa Fe', 'Staria', 'Terracan', 'Tucson', 'Veloster'],
  'Infiniti': ['Q30', 'Q50', 'Q60', 'Q70', 'QX30', 'QX50', 'QX70', 'QX80'],
  'Jaguar': ['E-Pace', 'F-Pace', 'F-Type', 'I-Pace', 'XE', 'XF', 'XJ'],
  'Jeep': ['Avenger', 'Cherokee', 'Commander', 'Compass', 'Gladiator', 'Grand Cherokee', 'Renegade', 'Wrangler'],
  'Kia': ['Carens', 'Ceed', 'EV6', 'EV9', 'Niro', 'Optima', 'Picanto', 'ProCeed', 'Rio', 'Seltos', 'Sorento', 'Soul', 'Sportage', 'Stinger', 'Stonic', 'Venga', 'XCeed'],
  'Lamborghini': ['Aventador', 'Countach', 'Gallardo', 'Huracan', 'Revuelto', 'Urus'],
  'Land Rover': ['Defender', 'Discovery', 'Discovery Sport', 'Freelander', 'Range Rover', 'Range Rover Evoque', 'Range Rover Sport', 'Range Rover Velar'],
  'Lexus': ['CT', 'ES', 'GS', 'IS', 'LC', 'LM', 'LS', 'LX', 'NX', 'RC', 'RX', 'RZ', 'UX'],
  'Maserati': ['Ghibli', 'GranCabrio', 'GranTurismo', 'Grecale', 'Levante', 'MC20', 'Quattroporte'],
  'Mazda': ['2', '3', '5', '6', 'CX-3', 'CX-30', 'CX-5', 'CX-60', 'CX-80', 'MX-30', 'MX-5'],
  'McLaren': ['540C', '570S', '600LT', '620R', '650S', '720S', '750S', 'Artura', 'GT', 'P1'],
  'Mercedes-Benz': ['A-Class', 'AMG GT', 'B-Class', 'C-Class', 'CLA', 'CLE', 'CLS', 'E-Class', 'EQA', 'EQB', 'EQC', 'EQE', 'EQE SUV', 'EQS', 'EQS SUV', 'EQV', 'G-Class', 'GLA', 'GLB', 'GLC', 'GLC Coupe', 'GLE', 'GLE Coupe', 'GLS', 'S-Class', 'SL', 'SLC', 'SLK', 'Sprinter', 'V-Class', 'Vito'],
  'MG': ['3', '4', '5', 'Cyberster', 'EHS', 'HS', 'Marvel R', 'MG4', 'MG5', 'ZS', 'ZS EV'],
  'MINI': ['Clubman', 'Convertible', 'Countryman', 'Coupe', 'Hatch', 'John Cooper Works', 'Paceman', 'Roadster'],
  'Mitsubishi': ['ASX', 'Colt', 'Eclipse Cross', 'L200', 'Lancer', 'Outlander', 'Pajero', 'Space Star'],
  'Nissan': ['Ariya', 'Juke', 'Leaf', 'Micra', 'Navara', 'Note', 'NV200', 'NV300', 'Pathfinder', 'Primastar', 'Pulsar', 'Qashqai', 'Townstar', 'X-Trail'],
  'Opel': ['Adam', 'Astra', 'Combo', 'Corsa', 'Crossland', 'Grandland', 'Insignia', 'Karl', 'Meriva', 'Mokka', 'Movano', 'Vivaro', 'Zafira'],
  'Peugeot': ['108', '2008', '206', '207', '208', '3008', '301', '308', '408', '5008', '508', 'Boxer', 'Expert', 'Partner', 'Rifter', 'e-208', 'e-2008', 'e-308'],
  'Polestar': ['1', '2', '3', '4'],
  'Porsche': ['718 Boxster', '718 Cayman', '911', 'Cayenne', 'Cayenne Coupe', 'Macan', 'Panamera', 'Taycan', 'Taycan Cross Turismo'],
  'Renault': ['Arkana', 'Austral', 'Captur', 'Clio', 'Espace', 'Fluence', 'Grand Scenic', 'Kadjar', 'Kangoo', 'Koleos', 'Laguna', 'Master', 'Megane', 'Megane E-Tech', 'Rafale', 'Scenic', 'Scenic E-Tech', 'Symbioz', 'Talisman', 'Trafic', 'Twingo', 'Zoe'],
  'Rolls-Royce': ['Cullinan', 'Dawn', 'Ghost', 'Phantom', 'Spectre', 'Wraith'],
  'SEAT': ['Alhambra', 'Altea', 'Arona', 'Arosa', 'Ateca', 'Ibiza', 'Leon', 'Mii', 'Tarraco', 'Toledo'],
  'Skoda': ['Citigo', 'Elroq', 'Enyaq', 'Fabia', 'Kamiq', 'Karoq', 'Kodiaq', 'Octavia', 'Rapid', 'Roomster', 'Scala', 'Superb', 'Yeti'],
  'Smart': ['EQ fortwo', 'forfour', 'fortwo', '#1', '#3'],
  'SsangYong': ['Actyon', 'Korando', 'Musso', 'Rexton', 'Tivoli', 'Torres', 'XLV'],
  'Subaru': ['BRZ', 'Crosstrek', 'Forester', 'Impreza', 'Legacy', 'Levorg', 'Outback', 'Solterra', 'WRX', 'XV'],
  'Suzuki': ['Across', 'Alto', 'Baleno', 'Celerio', 'Fronx', 'Ignis', 'Jimny', 'S-Cross', 'Swace', 'Swift', 'SX4', 'Vitara'],
  'Tesla': ['Model 3', 'Model S', 'Model X', 'Model Y', 'Cybertruck'],
  'Toyota': ['Auris', 'Avensis', 'Aygo', 'Aygo X', 'bZ4X', 'C-HR', 'Camry', 'Corolla', 'Corolla Cross', 'GR Supra', 'GR86', 'Highlander', 'Hilux', 'Land Cruiser', 'Mirai', 'Prius', 'ProAce', 'ProAce City', 'RAV4', 'Supra', 'Yaris', 'Yaris Cross'],
  'Volkswagen': ['Amarok', 'Arteon', 'Caddy', 'California', 'Caravelle', 'CC', 'Crafter', 'e-Golf', 'Golf', 'ID.3', 'ID.4', 'ID.5', 'ID.7', 'ID. Buzz', 'Jetta', 'Multivan', 'Passat', 'Polo', 'Scirocco', 'Sharan', 'T-Cross', 'T-Roc', 'Taigo', 'Tiguan', 'Tiguan Allspace', 'Touareg', 'Touran', 'Transporter', 'Up'],
  'Volvo': ['C30', 'C40', 'C70', 'EX30', 'EX40', 'EX90', 'S40', 'S60', 'S80', 'S90', 'V40', 'V40 Cross Country', 'V50', 'V60', 'V60 Cross Country', 'V70', 'V90', 'V90 Cross Country', 'XC40', 'XC60', 'XC70', 'XC90'],
}

// ── Body Types ──────────────────────────────────────────────

export const AUTOVIT_BODY_TYPES = [
  { value: 'sedan', label: 'Sedan' },
  { value: 'suv', label: 'SUV' },
  { value: 'compact', label: 'Hatchback / Compact' },
  { value: 'combi', label: 'Break / Combi' },
  { value: 'coupe', label: 'Coupe' },
  { value: 'cabrio', label: 'Cabrio / Decapotabil' },
  { value: 'minivan', label: 'Monovolum / Minivan' },
  { value: 'city-car', label: 'City Car' },
  { value: 'small-car', label: 'Small Car' },
  { value: 'pickup', label: 'Pickup' },
  { value: 'van', label: 'Van / Utilitara' },
] as const

// ── Fuel Types ──────────────────────────────────────────────

export const AUTOVIT_FUEL_TYPES = [
  { value: 'petrol', label: 'Benzina' },
  { value: 'diesel', label: 'Diesel' },
  { value: 'electric', label: 'Electric' },
  { value: 'hybrid', label: 'Hibrid' },
  { value: 'plugin-hybrid', label: 'Hibrid Plug-In' },
  { value: 'petrol-lpg', label: 'Benzina + GPL' },
  { value: 'petrol-cng', label: 'Benzina + CNG' },
  { value: 'hydrogen', label: 'Hidrogen' },
] as const

// ── Gearbox / Transmission ─────────────────────────────────

export const AUTOVIT_GEARBOX_TYPES = [
  { value: 'manual', label: 'Manuala' },
  { value: 'automatic', label: 'Automata' },
  { value: 'dual-clutch', label: 'Dublu ambreiaj (DSG/PDK)' },
  { value: 'cvt', label: 'CVT' },
  { value: 'semi-automatic', label: 'Semi-automata' },
  { value: 'automated-manual', label: 'Manuala automatizata' },
] as const

// ── Drive Type ──────────────────────────────────────────────
// NOTE: Autovit API calls this "filter_enum_transmission" (confusingly)

export const AUTOVIT_DRIVE_TYPES = [
  { value: 'front-wheel', label: 'Fata (FWD)' },
  { value: 'rear-wheel', label: 'Spate (RWD)' },
  { value: 'all-wheel-permanent', label: '4x4 Permanent (AWD)' },
  { value: 'all-wheel-auto', label: '4x4 Automat' },
  { value: 'all-wheel-lock', label: '4x4 Blocabil' },
] as const

// ── Exterior Colors ─────────────────────────────────────────

export const AUTOVIT_COLORS = [
  { value: 'black', label: 'Negru' },
  { value: 'white', label: 'Alb' },
  { value: 'silver', label: 'Argintiu' },
  { value: 'grey', label: 'Gri' },
  { value: 'blue', label: 'Albastru' },
  { value: 'red', label: 'Rosu' },
  { value: 'green', label: 'Verde' },
  { value: 'brown', label: 'Maro' },
  { value: 'beige', label: 'Bej' },
  { value: 'yellow', label: 'Galben' },
  { value: 'orange', label: 'Portocaliu' },
  { value: 'gold', label: 'Auriu' },
  { value: 'violet', label: 'Violet / Mov' },
  { value: 'other', label: 'Alta culoare' },
] as const

// ── Interior Colors ─────────────────────────────────────────

export const AUTOVIT_INTERIOR_COLORS = [
  { value: 'black', label: 'Negru' },
  { value: 'beige', label: 'Bej / Crem' },
  { value: 'brown', label: 'Maro' },
  { value: 'grey', label: 'Gri' },
  { value: 'white', label: 'Alb' },
  { value: 'red', label: 'Rosu' },
  { value: 'blue', label: 'Albastru' },
  { value: 'other', label: 'Alta culoare' },
] as const

// ── Euro Emission Standards ─────────────────────────────────

export const AUTOVIT_EURO_STANDARDS = [
  { value: 'euro-6d', label: 'Euro 6d' },
  { value: 'euro-6d-temp', label: 'Euro 6d-TEMP' },
  { value: 'euro-6', label: 'Euro 6' },
  { value: 'euro-5', label: 'Euro 5' },
  { value: 'euro-4', label: 'Euro 4' },
  { value: 'euro-3', label: 'Euro 3' },
  { value: 'euro-2', label: 'Euro 2' },
  { value: 'euro-1', label: 'Euro 1' },
  { value: 'non-euro', label: 'Non-Euro' },
] as const

// ── Vehicle State (New / Used) ──────────────────────────────

export const AUTOVIT_VEHICLE_STATES = [
  { value: 'Nou', label: 'Nou' },
  { value: 'Rulat', label: 'Rulat (Second Hand)' },
] as const

// ── Doors ───────────────────────────────────────────────────

export const AUTOVIT_DOORS = [
  { value: '2', label: '2/3' },
  { value: '4', label: '4/5' },
  { value: '6', label: '6+' },
] as const

// ── Seats ───────────────────────────────────────────────────

export const AUTOVIT_SEATS = [
  { value: '2', label: '2' },
  { value: '4', label: '4' },
  { value: '5', label: '5' },
  { value: '6', label: '6' },
  { value: '7', label: '7' },
  { value: '8', label: '8' },
  { value: '9', label: '9+' },
] as const
