// Minimal type declarations for Strophe.js
// Since @types/strophejs doesn't exist, we'll add minimal types ourselves

declare module 'strophe.js' {
  export class Strophe {
    static Status: {
      ERROR: number;
      CONNECTING: number;
      CONNFAIL: number;
      AUTHENTICATING: number;
      AUTHFAIL: number;
      CONNECTED: number;
      DISCONNECTED: number;
      DISCONNECTING: number;
      ATTACHED: number;
      REDIRECT: number;
      CONNTIMEOUT: number;
    };

    static Connection: typeof Connection;
    static Builder: typeof Builder;

    static NS: {
      MUC: string;
      [key: string]: string;
    };

    static getBareJidFromJid(jid: string): string;
    static getResourceFromJid(jid: string): string;
    static getNodeFromJid(jid: string): string;
    static getDomainFromJid(jid: string): string;
  }

  export class Connection {
    constructor(service: string, options?: any);
    connect(jid: string, password: string, callback: (status: number, condition?: string) => void): void;
    disconnect(reason?: string): void;
    send(element: Element | Builder): void;
    addHandler(
      handler: (stanza: Element) => boolean,
      ns?: string | null,
      name?: string | null,
      type?: string | null,
      id?: string | null,
      from?: string | null,
      options?: any
    ): string;
    deleteHandler(handlerRef: string): void;
    sendIQ(iq: Element | Builder, callback?: (iq: Element) => boolean, errback?: (iq: Element) => boolean): string;
    flush(): void;
    jid: string;
    authenticated: boolean;
    connected: boolean;
  }

  export class Builder {
    constructor(name: string, attrs?: Record<string, string>);
    tree(): Element;
    up(): Builder;
    c(name: string, attrs?: Record<string, string>, text?: string): Builder;
    t(text: string): Builder;
    attrs(attrs: Record<string, string>): Builder;
  }

  export namespace $msg {
    function apply(thisArg: any, args: any[]): Builder;
  }

  export namespace $pres {
    function apply(thisArg: any, args: any[]): Builder;
  }

  export namespace $iq {
    function apply(thisArg: any, args: any[]): Builder;
  }

  export default Strophe;
}
