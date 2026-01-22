# Design Skills - Quick Reference

## CLI Commands

```bash
# Show current configuration
python scripts/manage_design_skills.py show

# Test if skills apply to a prompt
python scripts/manage_design_skills.py test "build a login form"

# Enable a skill
python scripts/manage_design_skills.py enable impeccable_style

# Disable a skill
python scripts/manage_design_skills.py disable ui_skills

# Get design review checklist
python scripts/manage_design_skills.py review
```

## Available Skills

| Skill | URL | What It Provides |
|-------|-----|------------------|
| **impeccable_style** | https://impeccable.style/ | Visual hierarchy, typography, color theory, spacing |
| **ui_skills** | http://ui-skills.com | UI constraints, form patterns, accessibility rules |
| **rams_ai** | https://www.rams.ai/ | Accessibility review, visual consistency, UI polish |

## Automatic Triggers

Design skills activate when prompts contain:

```
ui, interface, design, style, component, button, form,
navigation, layout, accessibility, accessible, responsive,
web, frontend, css, html
```

## Key Principles Applied

### Impeccable Style
- ✓ Visual hierarchy (size, weight, color)
- ✓ Typography (16px+, 1.5-1.8 line height)
- ✓ Color contrast (WCAG AA 4.5:1)
- ✓ Spacing scale (4px, 8px, 16px, 24px, 32px, 48px)

### UI Skills
- ✓ No disabled buttons (use validation messages)
- ✓ Descriptive labels (not "Submit")
- ✓ Inline validation (on blur)
- ✓ Loading states (all async ops)
- ✓ Clear error messages (with recovery)
- ✓ Mobile-first design
- ✓ 44x44px touch targets
- ✓ Visible focus indicators

### Rams.ai Checklist
**Accessibility:**
- Semantic HTML (header, nav, main, footer)
- ARIA labels
- Alt text
- Color contrast (4.5:1)
- Keyboard navigation
- Screen reader support

**Visual Consistency:**
- Consistent spacing scale
- Unified color palette
- Consistent typography
- Grid alignment
- Responsive breakpoints

**UI Polish:**
- Smooth transitions
- Loading states
- Error states
- Empty states
- Hover/active states
- Microinteractions

## Configuration File

Location: `config/design_skills.yaml`

```yaml
design_skills:
  impeccable_style:
    enabled: true  # Change to false to disable

  ui_skills:
    enabled: true

  rams_ai:
    enabled: true
```

## Example Usage

### Building a Form
```
/claude build a responsive login form with email and password
```

Claude applies:
- Mobile-first responsive design
- Inline validation on blur
- Clear error messages
- Accessible labels (ARIA)
- 44x44px touch targets
- Proper focus indicators
- Meaningful button labels

### Creating Navigation
```
/claude design a navigation bar for the app
```

Claude ensures:
- Semantic HTML (nav element)
- Keyboard navigation support
- Responsive breakpoints
- Hover/active states
- Visual hierarchy
- Accessible markup

### Reviewing Accessibility
```
/claude review the accessibility of my dashboard
```

Claude checks:
- WCAG AA compliance
- Color contrast ratios
- ARIA labels
- Keyboard navigation
- Screen reader compatibility
- Semantic HTML structure

## Testing

```bash
# Run tests
pytest tests/test_services/test_design_skills_service.py -v

# Expected: 17/17 tests passing
```

## Files

```
config/design_skills.yaml              # Configuration
src/services/design_skills_service.py  # Service implementation
scripts/manage_design_skills.py        # CLI tool
tests/test_services/test_design_skills_service.py  # Tests
docs/DESIGN_SKILLS.md                  # Full documentation
```

## Resources

- **Impeccable Style**: https://impeccable.style/
- **UI Skills**: http://ui-skills.com
- **Rams.ai**: https://www.rams.ai/
- **WCAG**: https://www.w3.org/WAI/WCAG21/quickref/
