# Sample Plan Output

This is an example of the output produced by the `/planwise plan` command.

---

## User Request

"Create a plan for adding user authentication to the application"

---

## Questions Asked

**Question 1: Plan Details**
- Name: "UserAuthentication"
- Abbreviation: "UA"
- Vision: "Implement secure user authentication with login, registration, and password reset functionality."

**Question 2: Scope**
- Sprints: 2
- First sprint: "Core Auth" - Login and registration

---

## Files Created

```
{plans-dir}/UserAuthentication/
├── UA-Master-Plan.md
└── Sprint-01-CoreAuth/
    ├── UA-S01-Sprint-Plan.md
    └── Session-01-Setup/
        ├── UA-S01-01-Orchestration.md
        ├── UA-S01-01-Recovery.md
        ├── UA-S01-01-01-Haiku-CheckExisting.md
        ├── UA-S01-01-02-Sonnet-CreateEntities.md
        ├── UA-S01-01-03-Sonnet-CreateController.md
        └── Outputs/
```

---

## Output Message

```
PLAN CREATED: UserAuthentication

**Abbreviation:** UA
**Location:** {plans-dir}/UserAuthentication/

**Files Created:**
- UA-Master-Plan.md
- Sprint-01-CoreAuth/UA-S01-Sprint-Plan.md
- Sprint-01-CoreAuth/Session-01-Setup/UA-S01-01-Orchestration.md
- Sprint-01-CoreAuth/Session-01-Setup/UA-S01-01-Recovery.md
- Sprint-01-CoreAuth/Session-01-Setup/UA-S01-01-01-Haiku-CheckExisting.md (task file)
- Sprint-01-CoreAuth/Session-01-Setup/UA-S01-01-02-Sonnet-CreateEntities.md (task file)
- Sprint-01-CoreAuth/Session-01-Setup/UA-S01-01-03-Sonnet-CreateController.md (task file)
- Sprint-01-CoreAuth/Session-01-Setup/Outputs/ (folder)

**Task Files Created:** 3 files (one per task)

**Next Steps:**
1. Review and refine the Master Plan
2. Review task files for completeness
3. Execute Session-01 using `/execute` or manually following READ-CONFIRM-ACT
```

---

## Example Master Plan Content

```markdown
# UserAuthentication Master Plan

**Plan Abbreviation:** UA
**Status:** READY_TO_EXECUTE
**Created:** 2026-02-02

---

## Vision

Implement secure user authentication with login, registration, and password reset functionality. This enables user accounts for the application.

---

## Sprint Overview

| Sprint | Name | Purpose | Sessions | Status |
|--------|------|---------|----------|--------|
| 01 | CoreAuth | Login and registration | 2 | ⏳ NOT STARTED |
| 02 | AdvancedAuth | Password reset and 2FA | 1 | ⏳ NOT STARTED |

**Total Sessions:** 3
**Prerequisite For:** None - standalone project

---

## Success Criteria

### Sprint-01 Complete When:
- [ ] User entity created with password hash
- [ ] Login controller functional
- [ ] Registration flow working
- [ ] Tests pass

### Project Complete When:
- [ ] All sprints complete
- [ ] User can login, register, and reset password
```
