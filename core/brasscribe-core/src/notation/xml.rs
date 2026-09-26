//! A small XML element tree and pretty printer.

#[derive(Clone, Debug, Default)]
pub struct El {
    pub name: String,
    pub attrs: Vec<(String, String)>,
    pub text: Option<String>,
    pub children: Vec<El>,
}

impl El {
    pub fn new(name: &str) -> El {
        El { name: name.to_string(), ..Default::default() }
    }

    pub fn text(name: &str, text: impl Into<String>) -> El {
        El { name: name.to_string(), text: Some(text.into()), ..Default::default() }
    }

    pub fn attr(mut self, k: &str, v: impl Into<String>) -> El {
        self.set(k, v);
        self
    }

    pub fn set(&mut self, k: &str, v: impl Into<String>) {
        let v = v.into();
        match self.attrs.iter_mut().find(|(n, _)| n == k) {
            Some(e) => e.1 = v,
            None => self.attrs.push((k.to_string(), v)),
        }
    }

    pub fn child(mut self, c: El) -> El {
        self.children.push(c);
        self
    }

    pub fn push(&mut self, c: El) {
        self.children.push(c);
    }

    pub fn write(&self, level: usize, out: &mut String) {
        for _ in 0..level {
            out.push_str("  ");
        }
        out.push('<');
        out.push_str(&self.name);
        for (k, v) in &self.attrs {
            out.push(' ');
            out.push_str(k);
            out.push_str("=\"");
            escape(v, true, out);
            out.push('"');
        }
        if self.children.is_empty() && self.text.is_none() {
            out.push_str(" />\n");
            return;
        }
        out.push('>');
        if let Some(t) = &self.text {
            escape(t, false, out);
        }
        if !self.children.is_empty() {
            out.push('\n');
            for c in &self.children {
                c.write(level + 1, out);
            }
            for _ in 0..level {
                out.push_str("  ");
            }
        }
        out.push_str("</");
        out.push_str(&self.name);
        out.push_str(">\n");
    }
}

fn escape(s: &str, attr: bool, out: &mut String) {
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' if attr => out.push_str("&quot;"),
            c => out.push(c),
        }
    }
}
