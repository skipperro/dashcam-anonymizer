# Dashcam Anonymizer Frontend

A modern React + Next.js frontend application for the Dashcam Anonymizer system. Built as a Single Page Application (SPA) with static export capability.

## 🚀 Phase 1: Core Foundation & Setup ✅

**Status**: Complete

**Implemented Features**:
- ✅ Next.js 14+ project with TypeScript and App Router
- ✅ Tailwind CSS with purple color scheme and custom design tokens
- ✅ Project structure with organized folders (`app/`, `components/`, `lib/`, etc.)
- ✅ Base UI components (Button, Card) with Headless UI integration
- ✅ Static export capability (`output: 'export'`)
- ✅ ESLint, Prettier, and development tools configured
- ✅ Initial routing structure for marketing and dashboard sections
- ✅ Theme system foundation (light/dark mode)
- ✅ I18n infrastructure (EN, PL, DE languages)
- ✅ Working navigation with Header and Footer
- ✅ Docker configuration for production deployment

## 🏗️ Architecture

### Technology Stack
- **Framework**: Next.js 14+ with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS + Headless UI
- **State Management**: Zustand + TanStack Query (configured)
- **Theme System**: Custom React Context with localStorage persistence
- **Internationalization**: Custom i18n provider (EN, PL, DE)
- **Icons**: Lucide React
- **Build**: Static export (`output: 'export'`)

### Project Structure
```
src/
├── app/                    # Next.js App Router
│   ├── page.tsx           # Homepage
│   ├── contact/           # Contact page
│   ├── dashboard/         # Dashboard page
│   ├── layout.tsx         # Root layout
│   └── globals.css        # Global styles
├── components/            # Reusable components
│   ├── ui/               # Base UI components (Button, Card)
│   ├── layout/           # Layout components (Header, Footer)
│   └── providers/        # Context providers (Theme, I18n, Query)
├── lib/                  # Utilities and configurations
│   ├── utils.ts         # Utility functions
│   └── types.ts         # TypeScript type definitions
└── types/               # Global type definitions
    └── index.ts
```

## 🎨 Theming

### Color Scheme
The application uses a purple-based color scheme with full dark/light mode support:

- **Primary**: Purple-500 (#8b5cf6) / Purple-400 (#a78bfa)
- **Background**: White / Dark Blue (#0f0f23)
- **Foreground**: Dark Blue / Light Gray
- **Cards**: White / Dark Gray (#1e1e2e)

### Theme Features
- ✅ Automatic system preference detection
- ✅ Manual theme toggle
- ✅ localStorage persistence
- ✅ Smooth transitions
- ✅ WCAG 2.1 AA contrast compliance

## 🌍 Internationalization

### Supported Languages
- 🇺🇸 **English (EN)** - Default
- 🇵🇱 **Polish (PL)** - Polski
- 🇩🇪 **German (DE)** - Deutsch

### Features
- ✅ Browser language detection
- ✅ Manual language switching
- ✅ localStorage persistence
- ✅ Fallback to English for missing translations

## 🛠️ Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup
```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Start production preview
npm start
```

### Available Scripts
- `npm run dev` - Start development server
- `npm run build` - Build for production (static export)
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript checks

## 🐳 Docker Deployment

### Build Docker Image
```bash
docker build -t dashcam-frontend .
```

### Run Container
```bash
docker run -p 80:80 dashcam-frontend
```

The container uses nginx to serve the static files with:
- ✅ SPA routing support
- ✅ Gzip compression
- ✅ Static asset caching
- ✅ Security headers

## 📋 Implementation Roadmap

### ✅ Phase 1: Core Foundation & Setup (Complete)
- Project structure and basic infrastructure
- Theme system and internationalization
- Base UI components and navigation
- Static export capability

### 📅 Phase 2: Theme System & i18n Infrastructure
- Enhanced theme configuration
- Complete translation management
- Advanced internationalization features

### 📅 Phase 3: Homepage & Contact Pages (Marketing)
- Complete homepage with hero section
- Contact form with backend integration
- SEO optimization

### 📅 Phase 4: Dashboard Foundation & Navigation
- Dashboard layout and navigation
- Video list components
- State management integration

### 📅 Phase 5: File Upload & Processing Settings
- Drag-and-drop file upload
- Processing configuration interface
- Upload progress tracking

### 📅 Phase 6: Real-time Updates & WebSocket Integration
- WebSocket client implementation
- Real-time progress updates
- Notification system

### 📅 Phase 7: Video Management & Download
- Video download functionality
- Video actions and management
- Bulk operations

### 📅 Phase 8: Performance Optimization & Error Handling
- Code splitting and lazy loading
- Comprehensive error boundaries
- Performance monitoring

### 📅 Phase 9: Accessibility & Final Polish
- WCAG 2.1 AA compliance
- Screen reader optimization
- Keyboard navigation

### 📅 Phase 10: Integration Testing & Deployment
- End-to-end testing
- Production deployment
- Performance validation

## 🎯 Current Capabilities

### Working Features
- ✅ Responsive design with mobile-first approach
- ✅ Dark/light theme switching with smooth transitions
- ✅ Multi-language support (EN, PL, DE)
- ✅ Navigation between pages
- ✅ Purple color scheme with proper contrast
- ✅ Static export for CDN deployment
- ✅ Docker containerization

### Sample Pages
- **Homepage**: Hero section with feature cards
- **Contact**: Placeholder for contact form
- **Dashboard**: Placeholder for video management

## 🔧 Configuration

### Environment Variables
```bash
# API Configuration (for future phases)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
NEXT_PUBLIC_DEFAULT_LANGUAGE=en
```

### Build Configuration
The application is configured for static export:
- `output: 'export'` in next.config.js
- Trailing slashes enabled for better CDN support
- Image optimization disabled for static hosting

## 🚀 Next Steps

1. **Phase 2**: Implement enhanced theming and complete i18n infrastructure
2. **Backend Integration**: Set up API client for backend communication
3. **Component Library**: Expand UI components with forms and interactions
4. **Testing**: Add comprehensive testing suite

## 📝 Notes

- The application is built with progressive enhancement in mind
- All client-side features gracefully degrade for static generation
- The codebase follows Next.js 14 best practices with App Router
- TypeScript strict mode is enabled for type safety
