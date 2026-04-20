/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
const push = jest.fn();
const replace = jest.fn();
const back = jest.fn();

export const useRouter = () => ({ push, replace, back, prefetch: jest.fn() });
export const usePathname = () => "/";
export const useParams = () => ({});
export const useSearchParams = () => new URLSearchParams();
