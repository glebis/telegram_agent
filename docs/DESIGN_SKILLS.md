# Design Skills Integration

This document describes the design skills system integrated into Verity's Claude Code functionality.

## Quick Reference

```bash
# CLI Commands
python scripts/manage_design_skills.py show              # View configuration
python scripts/manage_design_skills.py test "prompt"     # Test if skills apply
python scripts/manage_design_skills.py enable <skill>    # Enable a skill
python scripts/manage_design_skills.py disable <skill>   # Disable a skill
python scripts/manage_design_skills.py review            # Get design checklist
```

| Skill | URL | What It Provides |
|-------|-----|------------------|
| **impeccable_style** | https://impeccable.style/ | Visual hierarchy, typography, color theory, spacing |
| **ui_skills** | http://ui-skills.com | UI constraints, form patterns, accessibility rules |
| **rams_ai** | https://www.rams.ai/ | Accessibility review, visual consistency, UI polish |

## Overview

The design skills system enhances Claude Code with best practices and guidance from three industry-leading design resources:

1. **[Impeccable Style](https://impeccable.style/)** - Design fluency for AI coding tools
2. **[UI Skills](http://ui-skills.com)** - Opinionated constraints for building better interfaces
3. **[Rams.ai](https://www.rams.ai/)** - A design engineer for your coding agent

## How It Works

### Automatic Enhancement

When you send a prompt to Claude Code that involves UI/UX work, the system automatically:

1. **Detects design-related keywords** in your prompt (e.g., "build a form", "design a button", "create navigation")
2. **Enhances the system prompt** with relevant design guidance
3. **Provides review checklists** for accessibility, consistency, and polish
4. **Offers to fix issues** with specific code examples

### Trigger Keywords

Design skills are applied when prompts include terms like:
- UI, interface, design, component
- Button, form, navigation, modal
- Style, layout, responsive
- Accessibility, WCAG
- Frontend, web, CSS, HTML

### Integration Points

```python
# In claude_code_service.py
from .design_skills_service import get_design_system_prompt

# System prompt is automatically enhanced
design_guidance = get_design_system_prompt()
telegram_system_prompt += "\n\n" + design_guidance
```

## Design Systems

### 1. Impeccable Style

Provides foundational design principles:

#### Visual Hierarchy
- Use size, weight, and color to establish importance
- Create clear focal points and visual flow
- Maintain consistent spacing and alignment
- Use whitespace purposefully

#### Typography
- Use max 2-3 font families
- Maintain readable font sizes (16px+ for body text)
- Use appropriate line heights (1.5-1.8 for body)
- Create clear type hierarchy
- Ensure sufficient contrast (WCAG AA minimum)

#### Color Palette
- Use a limited, cohesive color palette
- Ensure WCAG AA contrast ratios (4.5:1 for text)
- Consider color blindness accessibility
- Use color purposefully, not decoratively
- Maintain brand consistency

#### Spacing Rhythm
- Use a spacing scale (e.g., 4px, 8px, 16px, 24px, 32px, 48px)
- Maintain consistent padding and margins
- Group related elements with proximity
- Separate sections with adequate whitespace

### 2. UI Skills

Prevents common UI pitfalls with opinionated constraints:

| Constraint | Rule | Rationale |
|------------|------|-----------|
| **Avoid Disabled Buttons** | Don't disable buttons - use validation messages instead | Disabled buttons provide no feedback on why they're disabled |
| **Meaningful Labels** | Use descriptive button labels, not generic 'Submit' or 'OK' | Users should know what action they're taking |
| **Inline Validation** | Validate form fields on blur, not just on submit | Early feedback prevents frustration |
| **Loading States** | Always show loading states for async operations | Users need feedback that their action was received |
| **Error Recovery** | Provide clear error messages with recovery steps | Users need to know what went wrong and how to fix it |
| **Mobile First** | Design for mobile first, enhance for desktop | Ensures usability on smallest screens |
| **Touch Targets** | Minimum 44x44px touch targets for interactive elements | Ensures accessibility and usability on touch devices |
| **Focus Indicators** | Always show visible focus indicators for keyboard navigation | Critical for keyboard and screen reader users |

### 3. Rams.ai

Comprehensive review checklist for quality assurance:

#### Accessibility Checklist
- ✓ Semantic HTML elements (header, nav, main, footer, article)
- ✓ ARIA labels for interactive elements
- ✓ Alt text for all images
- ✓ Color contrast ratios meet WCAG AA (4.5:1)
- ✓ Keyboard navigation support (tab order, focus states)
- ✓ Screen reader compatibility
- ✓ Form labels and error messages

#### Visual Consistency Checklist
- ✓ Consistent spacing scale throughout
- ✓ Unified color palette
- ✓ Consistent typography (font families, sizes, weights)
- ✓ Aligned elements on a grid
- ✓ Consistent component styling
- ✓ Responsive breakpoints

#### UI Polish Checklist
- ✓ Smooth transitions and animations
- ✓ Loading states for all async operations
- ✓ Error states with recovery options
- ✓ Empty states with helpful guidance
- ✓ Hover and active states for interactive elements
- ✓ Microinteractions for user feedback
- ✓ Optimized images and assets

## Configuration

### Config File Location
`config/design_skills.yaml`

### Structure

```yaml
design_skills:
  impeccable_style:
    enabled: true
    url: https://impeccable.style/
    description: "Provides a suite of skills that guide AI to make better design decisions"
    priority: high

  ui_skills:
    enabled: true
    url: http://ui-skills.com
    description: "Checklist to prevent common yet undesirable UI patterns"
    priority: high

  rams_ai:
    enabled: true
    url: https://www.rams.ai/
    description: "Reviews for accessibility, visual inconsistencies, and UI polish"
    priority: high

integration:
  triggers:
    - "building UI components"
    - "creating web interfaces"
    - "designing forms"
    # ... more triggers

  mode: "system_prompt_enhancement"

  auto_review:
    enabled: true
    review_on_completion: true
    offer_fixes: true
```

## Management CLI

### View Configuration

```bash
python scripts/manage_design_skills.py show
```

Output:
```
=== Design Skills Configuration ===

IMPECCABLE_STYLE: ✓ ENABLED
  URL: https://impeccable.style/
  Description: Provides a suite of skills that guide AI to make better design decisions

UI_SKILLS: ✓ ENABLED
  URL: http://ui-skills.com
  Description: Checklist to prevent common yet undesirable UI patterns

RAMS_AI: ✓ ENABLED
  URL: https://www.rams.ai/
  Description: Reviews for accessibility, visual inconsistencies, and UI polish
```

### Test Skill Application

```bash
python scripts/manage_design_skills.py test "build a login form"
```

Output:
```
=== Testing Prompt ===
Prompt: build a login form

Would apply design skills: YES

=== Enhanced System Prompt ===
[Shows the complete enhanced system prompt that would be used]
```

### Enable/Disable Skills

```bash
# Enable a skill
python scripts/manage_design_skills.py enable impeccable_style

# Disable a skill
python scripts/manage_design_skills.py disable ui_skills
```

### Get Review Checklist

```bash
python scripts/manage_design_skills.py review
```

Output includes complete accessibility, consistency, and polish checklists.

## Usage Examples

### Example 1: Building a Form

**User prompt:**
```
Build a responsive login form with email and password fields
```

**What happens:**
1. System detects "form" keyword
2. Enhances prompt with design guidance
3. Claude applies:
   - Mobile-first responsive design
   - Inline validation on blur
   - Clear error messages
   - Accessible labels and ARIA attributes
   - 44x44px minimum touch targets
   - Proper focus indicators
   - Meaningful button labels

### Example 2: Creating Navigation

**User prompt:**
```
Design a navigation bar for the app
```

**What happens:**
1. System detects "navigation" and "design" keywords
2. Applies visual hierarchy principles
3. Ensures keyboard navigation support
4. Implements proper semantic HTML (nav element)
5. Creates responsive breakpoints
6. Adds hover/active states

### Example 3: Review Existing UI

**User prompt:**
```
Review the accessibility of my dashboard component
```

**What happens:**
1. Claude uses Rams.ai checklist
2. Checks all accessibility criteria
3. Identifies issues (e.g., missing ARIA labels, contrast ratios)
4. Offers specific fixes with code examples

## Customization

### Adding New Skills

Edit `config/design_skills.yaml`:

```yaml
design_skills:
  my_custom_skill:
    enabled: true
    url: https://example.com
    description: "Custom design guidance"
    priority: high

    skills:
      - name: "custom_principle"
        prompt: |
          Apply this custom principle:
          - Guidance here
          - More guidance
```

### Modifying Triggers

Add custom triggers to detect when skills should apply:

```yaml
integration:
  triggers:
    - "building UI components"
    - "my custom trigger phrase"
```

### Adjusting Review Checklists

Customize the Rams.ai review checklist:

```yaml
design_skills:
  rams_ai:
    review_checklist:
      accessibility:
        - "Custom accessibility check"
        - "Another custom check"
```

## Testing

Run the design skills service tests:

```bash
# Run all tests
pytest tests/test_services/test_design_skills_service.py -v

# Run specific test
pytest tests/test_services/test_design_skills_service.py::TestDesignSkillsService::test_should_apply_design_skills_ui_keywords -v
```

## Implementation Details

### Service Architecture

```
DesignSkillsService
├── _load_config()           # Load YAML configuration
├── should_apply_design_skills()  # Detect if skills are relevant
├── get_impeccable_style_prompt() # Generate Impeccable Style guidance
├── get_ui_skills_prompt()        # Generate UI Skills constraints
├── get_rams_ai_prompt()          # Generate Rams.ai checklist
├── get_enhanced_system_prompt()  # Combine all guidance
├── get_review_prompt()           # Generate review checklist
└── format_design_context()       # Format prompt with design context
```

### Integration Flow

```
User Prompt
    ↓
should_apply_design_skills()  ← Check keywords/triggers
    ↓
get_enhanced_system_prompt()  ← Build design guidance
    ↓
Claude Code Service           ← Enhanced system prompt
    ↓
Claude Response               ← Applies design principles
```

## Best Practices

### When to Use

Design skills are most valuable for:
- Building new UI components
- Creating web interfaces
- Designing forms and inputs
- Implementing navigation
- Reviewing accessibility
- Polishing user experience

### When to Disable

Consider disabling for:
- Backend/API development
- Database work
- Infrastructure tasks
- Non-UI scripting

### Combining with Other Tools

Design skills work well with:
- Component libraries (Tailwind, Material-UI)
- Accessibility testing tools
- Design systems (Figma, Sketch)
- Browser DevTools

## Resources

- **Impeccable Style**: https://impeccable.style/
- **UI Skills**: http://ui-skills.com
- **Rams.ai**: https://www.rams.ai/
- **WCAG Guidelines**: https://www.w3.org/WAI/WCAG21/quickref/
- **MDN Accessibility**: https://developer.mozilla.org/en-US/docs/Web/Accessibility

## Troubleshooting

### Skills Not Applied

**Problem**: Design skills not being applied to prompts

**Solution**:
1. Check if skills are enabled: `python scripts/manage_design_skills.py show`
2. Verify prompt contains trigger keywords
3. Test detection: `python scripts/manage_design_skills.py test "your prompt"`

### Configuration Not Loading

**Problem**: Config changes not taking effect

**Solution**:
1. Check YAML syntax is valid
2. Restart the bot service
3. Check logs for config loading errors

### Too Much Guidance

**Problem**: System prompt is too long with all skills enabled

**Solution**:
1. Disable less relevant skills for your use case
2. Customize config to remove unused sections
3. Use `priority: low` for optional guidance

## Future Enhancements

Planned improvements:
- [ ] Integration with design token systems
- [ ] Custom skill templates
- [ ] Per-user skill preferences
- [ ] Automated UI testing integration
- [ ] Design review GitHub Actions
- [ ] Visual regression testing
- [ ] Component library suggestions

## Contributing

To contribute new design skills or improvements:

1. Fork the repository
2. Create a feature branch
3. Add your skill to `config/design_skills.yaml`
4. Update `design_skills_service.py` if needed
5. Add tests in `tests/test_services/test_design_skills_service.py`
6. Update this documentation
7. Submit a pull request

## License

Design skills integration follows the same license as the main project. External resources (Impeccable Style, UI Skills, Rams.ai) are credited and linked appropriately.
