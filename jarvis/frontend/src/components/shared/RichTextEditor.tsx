import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Underline from '@tiptap/extension-underline'
import { useEffect, useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  Bold, Italic, Underline as UnderlineIcon, Strikethrough,
  List, ListOrdered, Quote, Link as LinkIcon, Undo, Redo,
  ChevronDown, Type, Heading2, Heading3,
} from 'lucide-react'

interface Props {
  content: string
  onChange: (html: string) => void
  placeholder?: string
  editable?: boolean
  className?: string
}

function ToolbarButton({
  onClick,
  active,
  children,
  title,
}: {
  onClick: () => void
  active?: boolean
  children: React.ReactNode
  title: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        'p-1.5 rounded hover:bg-accent transition-colors',
        active && 'bg-accent text-accent-foreground',
      )}
    >
      {children}
    </button>
  )
}

const headingOptions = [
  { label: 'Paragraph', icon: Type, value: 'paragraph' as const },
  { label: 'Heading 2', icon: Heading2, value: 'h2' as const },
  { label: 'Heading 3', icon: Heading3, value: 'h3' as const },
]

export function RichTextEditor({ content, onChange, placeholder, editable = true, className }: Props) {
  const [headingOpen, setHeadingOpen] = useState(false)
  const headingRef = useRef<HTMLDivElement>(null)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
      }),
      Underline,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: 'text-blue-500 underline cursor-pointer' },
      }),
    ],
    content,
    editable,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML())
    },
    editorProps: {
      attributes: {
        class: 'prose prose-sm dark:prose-invert max-w-none focus:outline-none min-h-[80px] px-3 py-2',
      },
    },
  })

  useEffect(() => {
    if (editor && content !== editor.getHTML()) {
      editor.commands.setContent(content)
    }
  }, [content, editor])

  useEffect(() => {
    if (editor) {
      editor.setEditable(editable)
    }
  }, [editable, editor])

  // Close heading dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (headingRef.current && !headingRef.current.contains(e.target as Node)) {
        setHeadingOpen(false)
      }
    }
    if (headingOpen) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [headingOpen])

  if (!editor) return null

  const addLink = () => {
    const url = window.prompt('Enter URL')
    if (url) {
      editor.chain().focus().setLink({ href: url }).run()
    }
  }

  const currentHeading = editor.isActive('heading', { level: 2 })
    ? 'h2'
    : editor.isActive('heading', { level: 3 })
      ? 'h3'
      : 'paragraph'

  const currentOption = headingOptions.find(o => o.value === currentHeading)!

  const setHeading = (value: 'paragraph' | 'h2' | 'h3') => {
    if (value === 'paragraph') {
      editor.chain().focus().setParagraph().run()
    } else if (value === 'h2') {
      editor.chain().focus().toggleHeading({ level: 2 }).run()
    } else {
      editor.chain().focus().toggleHeading({ level: 3 }).run()
    }
    setHeadingOpen(false)
  }

  return (
    <div className={cn('rounded-md border', className)}>
      {editable && (
        <div className="flex flex-wrap items-center gap-0.5 border-b px-2 py-1 bg-muted/30">
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive('bold')}
            title="Bold"
          >
            <Bold className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive('italic')}
            title="Italic"
          >
            <Italic className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleUnderline().run()}
            active={editor.isActive('underline')}
            title="Underline"
          >
            <UnderlineIcon className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleStrike().run()}
            active={editor.isActive('strike')}
            title="Strikethrough"
          >
            <Strikethrough className="h-4 w-4" />
          </ToolbarButton>

          <div className="w-px h-5 bg-border mx-1" />

          {/* Heading dropdown */}
          <div className="relative" ref={headingRef}>
            <button
              type="button"
              onClick={() => setHeadingOpen(!headingOpen)}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium hover:bg-accent transition-colors',
                currentHeading !== 'paragraph' && 'bg-accent text-accent-foreground',
              )}
              title="Text style"
            >
              <currentOption.icon className="h-4 w-4" />
              <span className="hidden sm:inline">{currentOption.label}</span>
              <ChevronDown className="h-3 w-3" />
            </button>
            {headingOpen && (
              <div className="absolute top-full left-0 mt-1 z-50 bg-popover border rounded-md shadow-md py-1 min-w-[140px]">
                {headingOptions.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setHeading(opt.value)}
                    className={cn(
                      'flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent transition-colors',
                      currentHeading === opt.value && 'bg-accent text-accent-foreground',
                    )}
                  >
                    <opt.icon className="h-4 w-4" />
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive('bulletList')}
            title="Bullet List"
          >
            <List className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            active={editor.isActive('orderedList')}
            title="Numbered List"
          >
            <ListOrdered className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            active={editor.isActive('blockquote')}
            title="Quote"
          >
            <Quote className="h-4 w-4" />
          </ToolbarButton>

          <div className="w-px h-5 bg-border mx-1" />

          <ToolbarButton onClick={addLink} active={editor.isActive('link')} title="Add Link">
            <LinkIcon className="h-4 w-4" />
          </ToolbarButton>

          <div className="w-px h-5 bg-border mx-1" />

          <ToolbarButton onClick={() => editor.chain().focus().undo().run()} title="Undo">
            <Undo className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton onClick={() => editor.chain().focus().redo().run()} title="Redo">
            <Redo className="h-4 w-4" />
          </ToolbarButton>
        </div>
      )}
      <EditorContent editor={editor} />
      {editable && !content && placeholder && (
        <style>{`.ProseMirror p.is-editor-empty:first-child::before { content: '${placeholder}'; float: left; color: hsl(var(--muted-foreground)); pointer-events: none; height: 0; }`}</style>
      )}
    </div>
  )
}

export function RichTextDisplay({ content, className }: { content: string; className?: string }) {
  if (!content || content === '<p></p>') {
    return null
  }
  return (
    <div
      className={cn('prose prose-sm dark:prose-invert max-w-none', className)}
      dangerouslySetInnerHTML={{ __html: content }}
    />
  )
}
