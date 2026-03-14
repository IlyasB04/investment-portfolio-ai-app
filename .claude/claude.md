# Portfolio AI App

## Project Overview

This project is a full stack RAG AI enabled financial portfolio management system.

The goal is to design, develop, and evaluate a working software prototype for a final year undergraduate computing project.

The system allows authenticated users to manage investment holdings, view portfolio analytics, and interact with AI driven financial insights.

The application must demonstrate real world software engineering quality, clear system architecture, and meaningful business value.

---

## Technology Stack

Frontend
- React
- TypeScript
- Vite
- Axios
- CSS Modules
- Custom design system using CSS variables

Backend
- Django
- Django REST Framework
- SimpleJWT authentication
- SQLite for development database

Infrastructure
- Local development proxy for API routing
- Git version control
- Modular project structure

---

## Core Functional Domains

Authentication
- JWT token based login
- Protected routes
- Global authentication context
- Secure API communication via Authorization header

Portfolio Management
- Create and manage holdings
- Portfolio summary aggregation
- Allocation and concentration metrics
- Real time dashboard updates

Financial Intelligence
- Forecast runs and performance evaluation
- Price snapshot integration
- AI conversational assistant planned using retrieval augmented generation

Audit and Governance
- AuditEvent logging for key user actions
- User scoped data access
- System traceability for evaluation chapter

---

## Engineering Principles

Code Quality
- TypeScript strict typing must be maintained
- Avoid any or unsafe casting
- Prefer clear explicit interfaces
- Components must be modular and reusable

Architecture
- Frontend must treat backend as source of truth
- Avoid duplicating business logic client side
- Use API driven state updates
- Maintain separation of UI state and domain state

User Experience
- Interface must resemble modern fintech platforms
- Minimal, professional dark theme styling
- Clear feedback for loading, success, and failure states
- Smooth modal and navigation interactions

Security
- All protected API calls must use JWT access token
- Token storage must be consistent under key "token"
- No sensitive logic should exist purely in frontend

---

## Development Workflow Expectations

When implementing new features Claude should:

1. Understand existing backend endpoints before generating frontend logic.
2. Prefer incremental feature additions rather than large rewrites.
3. Preserve existing working authentication and routing behaviour.
4. Ensure new UI elements integrate visually with current design system.
5. Provide brief reasoning for architectural decisions.

---

## Current Implementation Status

Completed
- Secure login flow
- Portfolio summary dashboard
- Axios API client with interceptor
- Development proxy routing
- Holdings API backend support

Next Planned Features
- Trade modal for creating holdings
- Portfolio mutation workflows
- Position aggregation logic
- Visual analytics charts
- AI conversational assistant panel

---

## Project Outcome Objective

The final system must be suitable for:

- Academic demonstration
- Supervisor review
- Evaluation of system usefulness
- Realistic fintech prototype presentation

Claude should prioritise clarity, correctness, and production quality over speed of generation.