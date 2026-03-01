const push = jest.fn();
const replace = jest.fn();
const back = jest.fn();

export const useRouter = () => ({ push, replace, back, prefetch: jest.fn() });
export const usePathname = () => "/";
export const useParams = () => ({});
export const useSearchParams = () => new URLSearchParams();
