# UX & Beautification Design

## Overview

Improve the video selection experience and apply a dark tech-style visual theme to the frontend.

## Part 1: Video Selection Improvements

### 1.1 Favorites / Quick Paths

**Location**: FileBrowser.vue top bar

- Add a horizontal quick-path bar above the file list
- Default shortcuts: Desktop, Downloads, Documents, Videos
- User can add/remove custom paths (stored in localStorage)
- Click a shortcut to navigate directly to that folder

**Implementation**:
- New component: `QuickPathBar.vue`
- localStorage key: `surveillance_quick_paths`
- Default paths resolved via API endpoint: `GET /api/system/paths`

### 1.2 Recent History

**Location**: Below VideoUploader

- Show last 5-10 analyzed videos
- Display: filename, analysis time, status (completed/failed)
- Click to re-analyze or view results
- Stored in localStorage

**Implementation**:
- New component: `RecentHistory.vue`
- localStorage key: `surveillance_recent_videos`
- Data: `{ id, filename, filePath, status, createdAt }`

### 1.3 Drag & Drop

**Location**: Full page overlay

- Drag video file anywhere on the page
- Show full-screen drop zone overlay with animation
- Accept video file extensions (.mp4, .avi, .mkv, .mov)
- On drop: validate file type, start analysis

**Implementation**:
- New composable: `useDragDrop.ts`
- Listen to `dragenter`, `dragover`, `drop` events on document
- Full-screen overlay with pulsing border animation

## Part 2: Dark Tech Theme

### Color Palette

| Role | Color | Hex |
|------|-------|-----|
| Background | Deep dark | `#0d1117` |
| Surface | Card bg | `#161b22` |
| Surface hover | Elevated | `#1c2128` |
| Border | Subtle | `rgba(255,255,255,0.1)` |
| Primary | Tech blue | `#58a6ff` |
| Success | Neon green | `#3fb950` |
| Warning | Amber | `#d29922` |
| Error | Red | `#f85149` |
| Text primary | Light | `#e6edf3` |
| Text secondary | Muted | `#8b949e` |

### Typography

- Font: Inter, system-ui, sans-serif
- Mono: JetBrains Mono, monospace (for paths, timestamps)

### Component Styling

**Cards**:
- Background: `#161b22`
- Border: `1px solid rgba(255,255,255,0.1)`
- Border-radius: `12px`
- Hover: box-shadow with blue glow

**Buttons**:
- Primary: gradient blue (`#58a6ff` → `#388bfd`)
- Secondary: transparent with border
- Hover: brightness increase + subtle glow

**Status Badges**:
- Completed: neon green with pulse animation
- Processing: blue with spinning animation
- Failed: red with shake animation
- Pending: muted gray

**Inputs**:
- Background: `#0d1117`
- Border: `rgba(255,255,255,0.2)`
- Focus: blue border + subtle glow

## Part 3: Timeline Enhancement

### Visual Design

- Gradient bar: green (start) → blue (end)
- Segments as rounded rectangles with slight elevation
- Hover: expand + show detail card
- Click: highlight segment + scroll to captures

### Detail Card (on hover)

```
┌─────────────────────────────┐
│ Segment 1                   │
│ 00:05 - 00:12 (7.0s)       │
│ Confidence: 92%             │
│ Detections: 15              │
└─────────────────────────────┘
```

### Animation

- Entry: segments slide in from left
- Hover: card fade in with scale
- Click: ripple effect

## Part 4: Interaction Effects

### Table Rows

- Hover: gradient background `rgba(88, 166, 255, 0.05)`
- Click: subtle scale `transform: scale(1.01)`
- Transition: `all 0.2s ease`

### Cards

- Hover: `translateY(-2px)` + blue shadow
- Entry: fade in + slide up

### Progress Bar

- Processing state: flowing light animation
- Completed: gradient fill with glow

## Part 5: Responsive Layout

### Breakpoints

- Mobile: `< 640px` — single column
- Tablet: `640px - 1024px` — two columns
- Desktop: `> 1024px` — full layout

### Mobile Adaptations

- Bottom navigation bar
- Full-width cards
- Collapsible sidebar
- Touch-friendly tap targets (44px min)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/styles/theme.css` | NEW | CSS variables, global styles |
| `frontend/src/components/QuickPathBar.vue` | NEW | Quick navigation shortcuts |
| `frontend/src/components/RecentHistory.vue` | NEW | Recent analysis history |
| `frontend/src/components/DropZone.vue` | NEW | Drag & drop overlay |
| `frontend/src/composables/useDragDrop.ts` | NEW | Drag & drop composable |
| `frontend/src/composables/useRecentHistory.ts` | NEW | Recent history composable |
| `frontend/src/composables/useQuickPaths.ts` | NEW | Quick paths composable |
| `frontend/src/App.vue` | MODIFY | Apply dark theme, add drop zone |
| `frontend/src/components/VideoUploader.vue` | MODIFY | Add recent history, integrate drag |
| `frontend/src/components/FileBrowser.vue` | MODIFY | Add quick paths bar |
| `frontend/src/components/TimelineViewer.vue` | MODIFY | Enhanced visual design |
| `frontend/src/components/JobList.vue` | MODIFY | Dark theme, animations |
| `frontend/src/components/JobDetail.vue` | MODIFY | Dark theme, animations |
| `frontend/src/components/SegmentTable.vue` | MODIFY | Dark theme, hover effects |
| `frontend/src/components/CaptureGallery.vue` | MODIFY | Dark theme |
| `backend: GET /api/system/paths` | NEW | Return default system paths |
