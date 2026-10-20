# D4 skeleton: how content points at an M11 element

Draft for discussion, published with v0.1.0 so others can react early. Nothing here is built yet; the D4 note itself comes after D2.

## The question

m11-rdf gives every ICH M11 protocol element an IRI. Content that realises an element needs a way to say so: a USDM instance in a study definition, a section of a protocol document, a field in a sponsor template.

## The one link

One property, from the content to the element:

| From | Link | To |
| --- | --- | --- |
| a USDM instance (study publisher's IRI) | realises | `m11:C217344.C25212` (Endpoint, namespace Section 3) |
| a document section | realises | `m11:C217272.C218527` (section 3.1) |
| a template field | realises | an element IRI |

The property is not defined yet. Open: an m11-rdf property, or an existing one (for example `dcterms:conformsTo`); and whether one property serves both elements and sections.

## Element is not instance

The element is the slot in M11; the instance is one study's content in that slot. Instance identity = element + scope + version:

- **Scope** is the study design, cohort or sub-study the content belongs to, not the document. A repeating section (3.2.X, one per secondary objective) gives one instance per repetition within a scope.
- **Version** is the study definition version the content is part of.
- Instance IRIs stay the study publisher's choice (usdm-rdf D7).

## Conformance checks need a scope rule

The Technical Specification states conformance per block, for example Endpoint: Required in 3.1.X, Conditional in 3.2.X. A check such as "required once" needs to know: once per what. Proposal to discuss: once per scope (study design, cohort or sub-study), per repetition where the section repeats.

## Master protocols

M11 treats a master protocol as an indicator element on one protocol (Master Protocol Indicator). USDM allows several study designs per study version. The scope rule above is meant to cover sub-studies as scopes. No public example study has a master protocol, so this is untested.

## Elements outside M11

Design elements that live mainly in USDM structure (encounters, activities, timings, schedule) have few or no M11 elements. They get elements in their own namespace (a sponsor's or a project's), linked to USDM by the same kind of mapping statement as M11 elements (D2, SSSOM), not by `skos:broadMatch` to OWL properties.

## The chain

```
design element (USDM instance) --realises--> M11 element (m11-rdf) --D2 mapping--> USDM class or attribute (usdm-rdf)
                                                  |
                                                  +--in section--> M11 section (m11-rdf) <--realises-- document section
```

With this chain, two representations of the same design element (USDM, FHIR, a sponsor template, a document) are related through the element they share, instead of through pairwise spreadsheets.
