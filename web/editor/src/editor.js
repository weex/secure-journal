import { Editor } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";

window.JournalEditor = {
  mount(element, options) {
    const editor = new Editor({
      element,
      extensions: [
        StarterKit,
        Placeholder.configure({ placeholder: options.placeholder || "" }),
      ],
      content: options.content || "",
      onUpdate() {
        if (options.onChange) options.onChange(editor.getJSON());
      },
    });
    return {
      getJSON: () => editor.getJSON(),
      setContent: (doc) => editor.commands.setContent(doc || ""),
      chain: () => editor.chain(),
      isActive: (name, attrs) => editor.isActive(name, attrs),
      destroy: () => editor.destroy(),
    };
  },
};
