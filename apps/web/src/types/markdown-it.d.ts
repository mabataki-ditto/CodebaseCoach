declare module 'markdown-it' {
  export interface MarkdownItOptions {
    html?: boolean
    linkify?: boolean
    breaks?: boolean
    highlight?: (code: string, language: string) => string
  }

  export default class MarkdownIt {
    utils: {
      escapeHtml(value: string): string
    }

    constructor(options?: MarkdownItOptions)
    render(content: string): string
  }
}
