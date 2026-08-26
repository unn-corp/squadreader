#define _GNU_SOURCE

#include <sys/prctl.h>

/* The container image intentionally does not need the Linux kernel header
 * package just to compile this tiny observer. glibc exposes the prctl call;
 * provide the one Linux-specific sentinel when its wrapper does not expose
 * the constant. */
#ifndef PR_SET_PTRACER_ANY
#define PR_SET_PTRACER_ANY ((unsigned long)-1)
#endif

/*
 * This constructor runs in the launched server process only. It allows a
 * read-only observer such as SquadReader to inspect that target process.
 * It does not change the host-wide ptrace policy, change ptrace_scope, or
 * grant ptrace permission to every process on the host.
 *
 * PR_SET_PTRACER_ANY is deliberately used because the observer PID is not
 * known when LD_PRELOAD constructors run. The observer must still use its
 * read-only attach/read path; this helper does not make writes safe or
 * enforce the observer's behavior.
 */
__attribute__((constructor))
static void gc_allow_ptrace_observer(void)
{
    (void)prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY);
}
